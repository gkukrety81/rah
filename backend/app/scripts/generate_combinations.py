# backend/app/scripts/generate_combinations.py
from __future__ import annotations
import argparse
import asyncio
import itertools
import json
import os
import random
import signal
import time
from typing import List, Tuple, Optional, Dict, Any

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.ollama_client import ollama_generate

# ============================================================
# Single LLM call per triad (faster + more consistent)
# ============================================================

ONE_CALL_SYS = (
    "You are generating structured clinical scaffolding from three clinician-authored "
    "base profiles (physiology programs). "
    "Return ONE compact JSON object and NOTHING else. "
    "Schema:\n"
    "{\n"
    '  "combination": "Concise title (<=140 chars)",\n'
    '  "analysis": "1–2 sentence neutral blurb",\n'
    '  "potential_indications": {\n'
    '    "Physical": ["..."],\n'
    '    "Psychological/Emotional": ["..."],\n'
    '    "Functional": ["..."]\n'
    "  },\n"
    '  "recommendations": ["bullet", "bullet", "..."]\n'
    "}\n"
    "Rules:\n"
    "- JSON ONLY. No prose outside JSON.\n"
    "- 8–12 total potential indications across the three groups; short, specific YES/NO style items.\n"
    "- 5–8 recommendation bullets (diet, lifestyle, emotional regulation, stress, follow-up).\n"
    "Neutral, professional tone."
)

# ============================================================
# Helpers
# ============================================================

def _normalize_triad(ids: List[float]) -> Tuple[float, float, float]:
    return tuple(sorted(float(x) for x in ids))

def _combo_key(triad: Tuple[float, float, float]) -> str:
    return ",".join(f"{x:.2f}" for x in triad)

def _truncate(s: str, max_chars: int = 1200) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_chars else s[: max_chars - 3] + "..."

# ============================================================
# Database helpers
# ============================================================

async def ensure_table_once(session: AsyncSession) -> None:
    # Create table and the unique index in two separate statements (asyncpg limitation)
    await session.execute(sa_text("""
                                  CREATE TABLE IF NOT EXISTS rah_schema.rah_combination_profiles (
                                                                                                     combination_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                      rah_ids NUMERIC(5,2)[] NOT NULL,
                                      combination_title TEXT,
                                      analysis TEXT,
                                      potential_indications JSONB,
                                      recommendations TEXT,
                                      created_at TIMESTAMPTZ DEFAULT NOW(),
                                      combo_key TEXT
                                      )
                                  """))
    await session.execute(sa_text("""
                                  CREATE UNIQUE INDEX IF NOT EXISTS ux_rah_combo_key
                                      ON rah_schema.rah_combination_profiles (combo_key)
                                  """))
    await session.commit()

async def fetch_all_program_codes(session: AsyncSession) -> List[float]:
    r = await session.execute(sa_text("""
                                      SELECT DISTINCT program_code
                                      FROM rah_schema.rah_base_profiles
                                      WHERE program_code IS NOT NULL
                                      ORDER BY program_code
                                      """))
    return [float(row[0]) for row in r.fetchall()]

async def fetch_base_profile(session: AsyncSession, program_code: float) -> str:
    # Prefer curated base profile; fall back to any mapped rah_item description/details
    r = await session.execute(sa_text("""
                                      SELECT profile_text
                                      FROM rah_schema.rah_base_profiles
                                      WHERE program_code = :pc
                                          LIMIT 1
                                      """), {"pc": int(program_code)})
    txt = r.scalar_one_or_none()
    if txt and str(txt).strip():
        return str(txt).strip()

    r = await session.execute(sa_text("""
                                      SELECT COALESCE(NULLIF(i.description, ''), i.details)
                                      FROM rah_schema.rah_item i
                                               JOIN rah_schema.rah_item_program ip ON ip.rah_id = i.rah_id
                                      WHERE ip.program_code = :pc
                                      ORDER BY i.rah_id
                                          LIMIT 1
                                      """), {"pc": int(program_code)})
    txt = r.scalar_one_or_none()
    return (txt or "").strip()

async def exists_by_key(session: AsyncSession, key: str) -> bool:
    r = await session.execute(sa_text("""
                                      SELECT 1
                                      FROM rah_schema.rah_combination_profiles
                                      WHERE combo_key = :k
                                          LIMIT 1
                                      """), {"k": key})
    return r.first() is not None

async def upsert_combination(session: AsyncSession, triad: Tuple[float, float, float], payload: Dict[str, Any]) -> None:
    await session.execute(sa_text("""
                                  INSERT INTO rah_schema.rah_combination_profiles
                                  (rah_ids, combination_title, analysis, potential_indications, recommendations)
                                  VALUES
                                      (:rah_ids, :title, :analysis, CAST(:pi AS jsonb), :reco)
                                      ON CONFLICT (combo_key) DO UPDATE
                                                                     SET combination_title = EXCLUDED.combination_title,
                                                                     analysis = EXCLUDED.analysis,
                                                                     potential_indications = EXCLUDED.potential_indications,
                                                                     recommendations = EXCLUDED.recommendations
                                  """), {
                              "rah_ids": list(triad),
                              "title": str(payload.get("combination", "")).strip() or "Combination",
                              "analysis": str(payload.get("analysis", "")).strip(),
                              "pi": json.dumps(payload.get("potential_indications", {
                                  "Physical": [], "Psychological/Emotional": [], "Functional": []
                              })),
                              "reco": "\n".join(payload.get("recommendations", [])),
                          })
    await session.commit()

# ============================================================
# Rate limit / retry
# ============================================================

class RateLimiter:
    def __init__(self, rps: float):
        self.rps = max(0.1, float(rps))
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self):
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            min_interval = 1.0 / self.rps
            wait = max(0.0, (self._last + min_interval) - now)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = loop.time()

async def call_ollama_with_retry(system: str, user: str, retries: int = 3) -> str:
    for attempt in range(retries + 1):
        try:
            return await ollama_generate(user, system=system)
        except Exception:
            if attempt == retries:
                raise
            # jittered backoff
            await asyncio.sleep(0.8 * (2 ** attempt) * (0.7 + random.random() * 0.6))

# ============================================================
# Payload validation
# ============================================================

def _validate_payload(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            data = json.loads(raw[start:end+1])
        else:
            return {
                "combination": "Combination",
                "analysis": raw.strip()[:400],
                "potential_indications": {
                    "Physical": [], "Psychological/Emotional": [], "Functional": []
                },
                "recommendations": []
            }

    combo = str(data.get("combination", "")).strip() or "Combination"
    analysis = str(data.get("analysis", "")).strip()
    pi = data.get("potential_indications") or {}
    phys = list(pi.get("Physical", [])) if isinstance(pi, dict) else []
    psyc = list(pi.get("Psychological/Emotional", [])) if isinstance(pi, dict) else []
    func = list(pi.get("Functional", [])) if isinstance(pi, dict) else []
    rec = data.get("recommendations") or []
    if isinstance(rec, str):
        rec = [x.strip("-• ") for x in rec.splitlines() if x.strip()]
    return {
        "combination": combo,
        "analysis": analysis,
        "potential_indications": {
            "Physical": phys, "Psychological/Emotional": psyc, "Functional": func
        },
        "recommendations": rec[:12]
    }

# ============================================================
# Progress tracking
# ============================================================

class Progress:
    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.bad = 0
        self.failed = 0
        self.start = time.time()
        self._lock = asyncio.Lock()
        self._last_print = 0.0

    async def tick(self, *, bad: bool = False, failed: bool = False):
        async with self._lock:
            self.done += 1
            if bad:
                self.bad += 1
            if failed:
                self.failed += 1
            now = time.time()
            if now - self._last_print >= 5:  # print every ~5s
                self._last_print = now
                rate = self.done / max(1e-9, (now - self.start))
                remaining = max(0, self.total - self.done)
                eta_s = remaining / max(1e-9, rate)
                eta_min = int(eta_s // 60)
                eta_sec = int(eta_s % 60)
                print(f"[progress] {self.done}/{self.total} "
                      f"({rate:.2f}/s, bad={self.bad}, failed={self.failed}) "
                      f"ETA ~ {eta_min}m {eta_sec}s")

    def final(self):
        dur = time.time() - self.start
        rate = self.done / max(1e-9, dur)
        print(f"[done] {self.done}/{self.total} in {dur:.1f}s "
              f"({rate:.2f}/s, bad={self.bad}, failed={self.failed})")

# ============================================================
# Generation logic (with --retry-bad)
# ============================================================

async def generate_for_triad(triad: Tuple[float, float, float],
                             limiter: RateLimiter,
                             dry_run: bool,
                             retry_bad: bool,
                             progress: Progress) -> None:
    async with SessionLocal() as session:
        key = _combo_key(triad)
        if await exists_by_key(session, key):
            await progress.tick()  # already exists counts as processed
            return

        # Fetch base profiles
        p1 = _truncate(await fetch_base_profile(session, triad[0]))
        p2 = _truncate(await fetch_base_profile(session, triad[1]))
        p3 = _truncate(await fetch_base_profile(session, triad[2]))

        context = (
            f"Program A ({triad[0]:.2f}) base profile:\n{p1}\n\n"
            f"Program B ({triad[1]:.2f}) base profile:\n{p2}\n\n"
            f"Program C ({triad[2]:.2f}) base profile:\n{p3}\n\n"
            "Return ONE JSON object now."
        )

        bad = False
        try:
            await limiter.acquire()
            raw = await call_ollama_with_retry(ONE_CALL_SYS, context)
            payload = _validate_payload(raw)

            # Retry once if bland “Combination” title
            if retry_bad and payload["combination"].lower() == "combination":
                bad = True
                await asyncio.sleep(1.0)
                raw = await call_ollama_with_retry(ONE_CALL_SYS, context)
                payload = _validate_payload(raw)

            if dry_run:
                print(f"[dry] {key} -> {payload['combination']!r}")
            else:
                await upsert_combination(session, triad, payload)

            await progress.tick(bad=bad)
        except Exception as e:
            print(f"[error] {key}: {e}")
            await progress.tick(failed=True)

# ============================================================
# Concurrency orchestration
# ============================================================

async def _producer(q: asyncio.Queue, codes: List[float], limit: Optional[int]) -> int:
    count = 0
    for a, b, c in itertools.combinations(codes, 3):
        triad = _normalize_triad([a, b, c])
        await q.put(triad)
        count += 1
        if limit and count >= limit:
            break
    workers = int(os.environ.get("GEN_WORKERS_COUNT", "4"))
    for _ in range(workers):
        await q.put(None)  # poison pill
    return count

async def _worker(idx: int,
                  q: asyncio.Queue,
                  limiter: RateLimiter,
                  dry_run: bool,
                  retry_bad: bool,
                  progress: Progress):
    while True:
        triad = await q.get()
        if triad is None:
            q.task_done()
            break
        try:
            await generate_for_triad(triad, limiter, dry_run, retry_bad, progress)
        finally:
            q.task_done()

# ============================================================
# Run modes
# ============================================================

async def run_ids(ids: str, dry_run: bool, retry_bad: bool) -> None:
    triad = _normalize_triad([float(x) for x in ids.split(",")])
    limiter = RateLimiter(2.0)
    progress = Progress(total=1)
    await generate_for_triad(triad, limiter, dry_run, retry_bad, progress)
    progress.final()

async def run_all(workers: int, rps: float, limit: Optional[int], dry_run: bool, retry_bad: bool):
    # Prepare table and fetch codes
    async with SessionLocal() as s:
        await ensure_table_once(s)
        codes = await fetch_all_program_codes(s)

    # Compute total triads (with optional limit)
    from math import comb
    total_triads = comb(len(codes), 3)
    if limit:
        total_triads = min(total_triads, limit)

    os.environ["GEN_WORKERS_COUNT"] = str(workers)
    q: asyncio.Queue = asyncio.Queue(maxsize=workers * 4)
    limiter = RateLimiter(rps)
    progress = Progress(total=total_triads)

    prod_task = asyncio.create_task(_producer(q, codes, limit))
    workers_tasks = [asyncio.create_task(_worker(i + 1, q, limiter, dry_run, retry_bad, progress))
                     for i in range(workers)]

    # Graceful Ctrl+C
    stop = asyncio.Event()
    def _cancel(*_): stop.set()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, _cancel)
            except NotImplementedError:
                pass
    except RuntimeError:
        pass

    # Wait for all tasks
    await asyncio.wait([prod_task, *workers_tasks], return_when=asyncio.ALL_COMPLETED)
    progress.final()

# ============================================================
# CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="Generate RAH triad combination profiles (single-call, retryable) with progress.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids", help="Three comma-separated RAH codes, e.g. 30,50,76")
    g.add_argument("--all3", action="store_true", help="Enumerate all 3-combinations from rah_base_profiles.program_code")

    ap.add_argument("--workers", type=int, default=4, help="Concurrent workers (default 4)")
    ap.add_argument("--rps", type=float, default=2.0, help="Global calls/sec across all workers")
    ap.add_argument("--limit", type=int, help="Max triads to process")
    ap.add_argument("--dry-run", action="store_true", help="Print only, no DB writes")
    ap.add_argument("--retry-bad", action="store_true", help="Retry once if LLM returns generic 'Combination' title")

    args = ap.parse_args()
    if args.ids:
        asyncio.run(run_ids(args.ids, args.dry_run, args.retry_bad))
    elif args.all3:
        asyncio.run(run_all(args.workers, args.rps, args.limit, args.dry_run, args.retry_bad))

if __name__ == "__main__":
    main()
