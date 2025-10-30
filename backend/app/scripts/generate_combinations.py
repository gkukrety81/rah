# backend/app/scripts/generate_combinations.py
from __future__ import annotations
import argparse
import asyncio
import itertools
import json
import os
import random
import signal
from typing import List, Tuple, Optional, Dict

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.ollama_client import ollama_generate

# ----------------------- Prompt templates -----------------------
COMBO_TITLE_SYS = (
    "You are given three physiology items (RAH IDs) with their base profiles. "
    "1) Propose a concise 'Combination' title (<=140 chars) that names the overlapping systems. "
    "2) Provide a 1–2 sentence neutral 'Analysis' blurb describing likely shared dysfunction.\n"
    "Return JSON only: {\"combination\":\"...\",\"analysis\":\"...\"}."
)

POTENTIAL_Q_SYS = (
    "From the three physiology base profiles, produce 8–12 crisp YES/NO items grouped across "
    "Physical, Psychological/Emotional, and Functional. Return JSON only with this exact shape:\n"
    "{\n"
    "  \"Physical\": [\"...\", \"...\"],\n"
    "  \"Psychological/Emotional\": [\"...\", \"...\"],\n"
    "  \"Functional\": [\"...\", \"...\"]\n"
    "}\n"
    "Avoid duplication. Keep items short and specific."
)

RECO_SYS = (
    "Based on the three physiology base profiles, write a short 'Recommendations for Rebalancing' "
    "section in a neutral, professional tone. Use 5–8 bullets covering diet, lifestyle, stress/"
    "emotional regulation, and follow-up. Return plain text only."
)

# ----------------------- Small utils -----------------------
def normalize_triad(ids: List[float]) -> Tuple[float, float, float]:
    a = sorted(float(x) for x in ids)
    return (a[0], a[1], a[2])

def combo_key(triad: Tuple[float, float, float]) -> str:
    return ",".join(f"{x:.2f}" for x in triad)

class RateLimiter:
    def __init__(self, rps: float):
        self.rps = max(0.1, float(rps))
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self):
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait = max(0.0, (self._last + 1.0/self.rps) - now)
            if wait:
                await asyncio.sleep(wait)
            self._last = loop.time()

# ----------------------- DB helpers -----------------------
async def ensure_table_once(session: AsyncSession):
    await session.execute(sa_text("""
                                  CREATE TABLE IF NOT EXISTS rah_schema.rah_combination_profiles(
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

async def exists_by_key(session: AsyncSession, key: str) -> bool:
    r = await session.execute(sa_text("""
                                      SELECT 1 FROM rah_schema.rah_combination_profiles
                                      WHERE combo_key = :k LIMIT 1
                                      """), {"k": key})
    return r.first() is not None

async def fetch_base_profile(session: AsyncSession, program_code: float) -> str:
    # curated profile first
    r = await session.execute(sa_text("""
                                      SELECT profile_text
                                      FROM rah_schema.rah_base_profiles
                                      WHERE program_code = :pc
                                          LIMIT 1
                                      """), {"pc": int(program_code)})
    txt = r.scalar_one_or_none()
    if txt and str(txt).strip():
        return str(txt).strip()

    # fallback – any item mapped to that program_code
    r = await session.execute(sa_text("""
                                      SELECT COALESCE(NULLIF(i.description,''), i.details) AS txt
                                      FROM rah_schema.rah_item i
                                               JOIN rah_schema.rah_item_program ip ON ip.rah_id = i.rah_id
                                      WHERE ip.program_code = :pc
                                      ORDER BY i.rah_id
                                          LIMIT 1
                                      """), {"pc": int(program_code)})
    return (r.scalar_one_or_none() or "").strip()

async def fetch_all_program_codes(session: AsyncSession) -> List[float]:
    r = await session.execute(sa_text("""
                                      SELECT DISTINCT program_code
                                      FROM rah_schema.rah_base_profiles
                                      WHERE program_code IS NOT NULL
                                      ORDER BY program_code
                                      """))
    return [float(x[0]) for x in r.fetchall()]

async def upsert_combination(session: AsyncSession,
                             triad: Tuple[float,float,float],
                             title: str,
                             analysis: str,
                             potential: Dict[str, List[str]],
                             reco: str):
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
                              "title": (title or "Combination").strip(),
                              "analysis": (analysis or "").strip(),
                              "pi": json.dumps(potential or {}),
                              "reco": (reco or "").strip()
                          })
    await session.commit()

# ----------------------- LLM w/ retries -----------------------
async def call_with_retry(system: str, user: str, retries: int = 4, base: float = 0.7) -> str:
    for i in range(retries + 1):
        try:
            return await ollama_generate(user, system=system)
        except Exception:
            if i == retries:
                raise
            jitter = base * (2 ** i) * (0.7 + random.random()*0.6)
            await asyncio.sleep(jitter)

def potential_empty_or_bad(p: Dict[str, List[str]]) -> bool:
    return not any((p or {}).get(k) for k in ("Physical", "Psychological/Emotional", "Functional"))

def title_bad(t: str) -> bool:
    t = (t or "").strip().lower()
    return (not t) or (t == "combination")

# ----------------------- One triad -----------------------
async def generate_for_triad(triad: Tuple[float,float,float],
                             limiter: RateLimiter,
                             retry_bad: bool = False,
                             dry_run: bool = False):
    key = combo_key(triad)
    async with SessionLocal() as s:
        if await exists_by_key(s, key) and not dry_run:
            return

        # fetch context
        p1 = await fetch_base_profile(s, triad[0])
        p2 = await fetch_base_profile(s, triad[1])
        p3 = await fetch_base_profile(s, triad[2])
        context = (
            f"RAH {triad[0]:.2f} – Base Profile:\n{p1}\n\n"
            f"RAH {triad[1]:.2f} – Base Profile:\n{p2}\n\n"
            f"RAH {triad[2]:.2f} – Base Profile:\n{p3}\n"
        )

    # combo+analysis
    await limiter.acquire()
    raw = await call_with_retry(COMBO_TITLE_SYS, f"{context}\nReturn JSON now.")
    title, analysis = "Combination", ""
    try:
        obj = json.loads(raw)
        title = (obj.get("combination") or "Combination").strip()
        analysis = (obj.get("analysis") or "").strip()
    except Exception:
        analysis = raw.strip()

    # potential
    await limiter.acquire()
    praw = await call_with_retry(POTENTIAL_Q_SYS, f"{context}\nReturn JSON now.")
    potential = {"Physical": [], "Psychological/Emotional": [], "Functional": []}
    try:
        pobj = json.loads(praw) or {}
        potential["Physical"] = list(pobj.get("Physical", []))
        potential["Psychological/Emotional"] = list(pobj.get("Psychological/Emotional", []))
        potential["Functional"] = list(pobj.get("Functional", []))
    except Exception:
        pass

    # optional retry on “bad”
    if retry_bad and (title_bad(title) or potential_empty_or_bad(potential)):
        await limiter.acquire()
        raw = await call_with_retry(COMBO_TITLE_SYS, f"{context}\nReturn JSON now.")
        try:
            obj = json.loads(raw)
            if title_bad(title):
                title = (obj.get("combination") or "Combination").strip()
            if not analysis:
                analysis = (obj.get("analysis") or "").strip()
        except Exception:
            pass

        await limiter.acquire()
        praw = await call_with_retry(POTENTIAL_Q_SYS, f"{context}\nReturn JSON now.")
        try:
            pobj = json.loads(praw) or {}
            if potential_empty_or_bad(potential):
                potential["Physical"] = list(pobj.get("Physical", []))
                potential["Psychological/Emotional"] = list(pobj.get("Psychological/Emotional", []))
                potential["Functional"] = list(pobj.get("Functional", []))
        except Exception:
            pass

    # recommendations
    await limiter.acquire()
    reco = await call_with_retry(RECO_SYS, f"{context}\nReturn text only.")

    if dry_run:
        print(f"[dry] {key} -> {title!r}")
        return

    async with SessionLocal() as s:
        await upsert_combination(s, triad, title, analysis, potential, reco)

# ----------------------- Orchestration -----------------------
async def run_ids(ids_str: str, dry_run: bool, retry_bad: bool):
    triad = normalize_triad([float(x) for x in ids_str.split(",")])
    limiter = RateLimiter(rps=2.0)
    await generate_for_triad(triad, limiter, retry_bad=retry_bad, dry_run=dry_run)

async def run_all(workers: int, rps: float, limit: Optional[int], retry_bad: bool, dry_run: bool):
    async with SessionLocal() as s:
        await ensure_table_once(s)
        codes = await fetch_all_program_codes(s)

    os.environ["GEN_WORKERS_COUNT"] = str(workers)
    q: asyncio.Queue = asyncio.Queue(maxsize=workers * 4)
    limiter = RateLimiter(rps=rps)

    async def producer():
        n = 0
        for a,b,c in itertools.combinations(codes, 3):
            await q.put(normalize_triad([a,b,c]))
            n += 1
            if limit and n >= limit:
                break
        for _ in range(workers):
            await q.put(None)  # poison
    async def worker(idx: int):
        processed = 0
        while True:
            triad = await q.get()
            if triad is None:
                break
            try:
                await generate_for_triad(triad, limiter, retry_bad=retry_bad, dry_run=dry_run)
            except Exception as e:
                print(f"[worker {idx}] {combo_key(triad)} failed: {e}")
            finally:
                processed += 1
                if processed % 50 == 0:
                    print(f"[worker {idx}] processed {processed}")
                q.task_done()

    prod = asyncio.create_task(producer())
    workers_tasks = [asyncio.create_task(worker(i+1)) for i in range(workers)]
    await asyncio.gather(prod, *workers_tasks)

def main():
    ap = argparse.ArgumentParser(description="Generate triad combination profiles into rah_combination_profiles.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids", help="Three comma-separated codes e.g. 30,50,76")
    g.add_argument("--all3", action="store_true", help="Enumerate across rah_base_profiles.program_code")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rps", type=float, default=2.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-bad", action="store_true", help="Retry once if title is 'Combination' or potential is empty")
    args = ap.parse_args()

    if args.ids:
        asyncio.run(run_ids(args.ids, dry_run=args.dry_run, retry_bad=args.retry_bad))
    else:
        asyncio.run(run_all(args.workers, args.rps, args.limit, args.retry_bad, args.dry_run))

if __name__ == "__main__":
    main()
