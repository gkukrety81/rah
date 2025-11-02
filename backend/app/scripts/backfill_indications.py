# backend/app/scripts/backfill_indications.py
from __future__ import annotations
import argparse
import asyncio
import json
import os
import random
from typing import Optional, List, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.ollama_client import ollama_generate

POTENTIAL_Q_SYS = (
    "From the combination title and analysis, produce 8–12 crisp YES/NO screening items grouped across "
    "Physical, Psychological/Emotional, and Functional. Return STRICT JSON with this exact shape:\n"
    "{\n"
    '  "Physical": ["..."],\n'
    '  "Psychological/Emotional": ["..."],\n'
    '  "Functional": ["..."]\n'
    "}\n"
    "Keep each item short, specific, and clinically neutral. No extra text, no markdown, only JSON."
)

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

async def fetch_batch(session: AsyncSession, only_missing: bool, limit: Optional[int]) -> List[Tuple[str, str, str]]:
    """
    Returns list of (combination_id, combination_title, analysis) to fill.
    """
    if only_missing:
        sql = """
              SELECT combination_id::text, COALESCE(combination_title,''), COALESCE(analysis,'')
              FROM rah_schema.rah_combination_profiles
              WHERE potential_indications IS NULL
                 OR potential_indications = '{}'::jsonb
              ORDER BY created_at ASC
                  LIMIT :lim
              """
    else:
        sql = """
              SELECT combination_id::text, COALESCE(combination_title,''), COALESCE(analysis,'')
              FROM rah_schema.rah_combination_profiles
              ORDER BY created_at ASC
                  LIMIT :lim
              """
    r = await session.execute(sa_text(sql), {"lim": limit or 500})
    return [(row[0], row[1], row[2]) for row in r.fetchall()]

def parse_potential(raw: str) -> Optional[dict]:
    try:
        obj = json.loads(raw)
        phys = list(obj.get("Physical", []))
        psych = list(obj.get("Psychological/Emotional", []))
        func = list(obj.get("Functional", []))
        if not isinstance(phys, list) or not isinstance(psych, list) or not isinstance(func, list):
            return None
        return {
            "Physical": [str(x) for x in phys][:12],
            "Psychological/Emotional": [str(x) for x in psych][:12],
            "Functional": [str(x) for x in func][:12],
        }
    except Exception:
        return None

async def call_ollama_with_retry(system_prompt: str, user_prompt: str, retries=3, base=0.8) -> str:
    for attempt in range(retries + 1):
        try:
            return await ollama_generate(user_prompt, system=system_prompt)
        except Exception:
            if attempt == retries:
                raise
            # jittered backoff
            delay = base * (2 ** attempt) * (0.7 + random.random() * 0.6)
            await asyncio.sleep(delay)

async def update_row(session: AsyncSession, cid: str, potential: dict) -> None:
    await session.execute(
        sa_text("""
                UPDATE rah_schema.rah_combination_profiles
                SET potential_indications = CAST(:pi AS jsonb)
                WHERE combination_id = :cid::uuid
                """),
        {"pi": json.dumps(potential, ensure_ascii=False), "cid": cid},
    )
    await session.commit()

async def worker(name: int,
                 q: asyncio.Queue,
                 limiter: RateLimiter,
                 retry_bad: bool,
                 counters: dict):
    while True:
        item = await q.get()
        if item is None:
            q.task_done()
            break
        cid, title, analysis = item
        try:
            await limiter.acquire()
            prompt = f"Combination: {title}\nAnalysis: {analysis}\n\nReturn JSON now."
            raw = await call_ollama_with_retry(POTENTIAL_Q_SYS, prompt)
            parsed = parse_potential(raw)

            if not parsed and retry_bad:
                # do one more try with tightened instruction
                await limiter.acquire()
                raw2 = await call_ollama_with_retry(
                    POTENTIAL_Q_SYS + "\nIf you failed before, ensure you output ONLY valid JSON.",
                    prompt
                )
                parsed = parse_potential(raw2)

            if parsed:
                async with SessionLocal() as s:
                    await update_row(s, cid, parsed)
                counters["updated"] += 1
            else:
                counters["bad"] += 1
        except Exception as e:
            counters["failed"] += 1
            print(f"[worker {name}] {cid} error: {e}")
        finally:
            q.task_done()
            total = counters["done"] = counters.get("done", 0) + 1
            if total % 25 == 0:
                print(f"[progress] {total} (updated={counters['updated']}, bad={counters['bad']}, failed={counters['failed']})")

async def main_async(only_missing: bool, limit: Optional[int], workers: int, rps: float, retry_bad: bool):
    # gather work
    async with SessionLocal() as s:
        batch = await fetch_batch(s, only_missing=only_missing, limit=limit)

    if not batch:
        print("[backfill] nothing to do")
        return

    q: asyncio.Queue = asyncio.Queue(maxsize=workers * 4)
    limiter = RateLimiter(rps=rps)
    counters = {"updated": 0, "bad": 0, "failed": 0, "done": 0}

    # enqueue
    for row in batch:
        await q.put(row)
    for _ in range(workers):
        await q.put(None)

    tasks = [asyncio.create_task(worker(i + 1, q, limiter, retry_bad, counters)) for i in range(workers)]
    await asyncio.gather(*tasks)
    print(f"[done] updated={counters['updated']} bad={counters['bad']} failed={counters['failed']}")

def main():
    ap = argparse.ArgumentParser(description="Backfill potential_indications for existing triads")
    ap.add_argument("--only-missing", action="store_true", help="Fill rows where potential_indications is NULL or {}")
    ap.add_argument("--limit", type=int, help="Max rows to process (default 500)")
    ap.add_argument("--workers", type=int, default=6, help="Concurrent workers (default 6)")
    ap.add_argument("--rps", type=float, default=2.0, help="Global LLM calls per second (default 2.0)")
    ap.add_argument("--retry-bad", action="store_true", help="Retry once if JSON parsing fails")
    args = ap.parse_args()

    asyncio.run(main_async(
        only_missing=args.only_missing,
        limit=args.limit,
        workers=args.workers,
        rps=args.rps,
        retry_bad=args.retry_bad
    ))

if __name__ == "__main__":
    main()
