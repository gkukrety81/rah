# backend/app/scripts/backfill_indications.py
from __future__ import annotations
import argparse, asyncio, json, os, random, itertools
from typing import Dict, List, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.ollama_client import ollama_generate

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

async def fetch_base_profile(session: AsyncSession, program_code: float) -> str:
    r = await session.execute(sa_text("""
                                      SELECT profile_text
                                      FROM rah_schema.rah_base_profiles
                                      WHERE program_code = :pc LIMIT 1
                                      """), {"pc": int(program_code)})
    txt = r.scalar_one_or_none()
    if txt and str(txt).strip():
        return str(txt).strip()

    r = await session.execute(sa_text("""
                                      SELECT COALESCE(NULLIF(i.description,''), i.details) AS txt
                                      FROM rah_schema.rah_item i
                                               JOIN rah_schema.rah_item_program ip ON ip.rah_id = i.rah_id
                                      WHERE ip.program_code = :pc
                                      ORDER BY i.rah_id LIMIT 1
                                      """), {"pc": int(program_code)})
    return (r.scalar_one_or_none() or "").strip()

def normalize_potential(raw: Dict) -> Dict[str, List[str]]:
    out = {
        "Physical": [],
        "Psychological/Emotional": [],
        "Functional": []
    }
    try:
        for k in out.keys():
            vals = raw.get(k, []) or []
            seen = set()
            clean = []
            for v in vals:
                s = " ".join(str(v).strip().split())
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    clean.append(s)
            out[k] = clean[:12]
    except Exception:
        pass
    return out

async def process_row(session: AsyncSession, comb_id: str, rah_ids: List[float]) -> bool:
    # Build context from base profiles
    p = []
    for code in rah_ids:
        p.append(await fetch_base_profile(session, float(code)))

    context = (
        f"RAH {rah_ids[0]:.2f} – Base Profile:\n{p[0] or '(no base profile)'}\n\n"
        f"RAH {rah_ids[1]:.2f} – Base Profile:\n{p[1] or '(no base profile)'}\n\n"
        f"RAH {rah_ids[2]:.2f} – Base Profile:\n{p[2] or '(no base profile)'}\n"
    )

    # Ask LLM
    raw = await ollama_generate(prompt=f"{context}\nReturn JSON now.", system=POTENTIAL_Q_SYS)
    try:
        obj = json.loads(raw)
    except Exception:
        obj = {}
    normalized = normalize_potential(obj)

    # Save
    await session.execute(sa_text("""
                                  UPDATE rah_schema.rah_combination_profiles
                                  SET potential_indications = CAST(:pi AS jsonb)
                                  WHERE combination_id = :id::uuid
                                  """), {"pi": json.dumps(normalized), "id": comb_id})
    return True

async def run(limit: int | None, only_missing: bool, rps: float):
    # crude global rate limiter
    min_interval = max(0.2, 1.0 / float(rps))

    async with SessionLocal() as session:
        q = """
            SELECT combination_id::text, rah_ids
            FROM rah_schema.rah_combination_profiles \
            """
        if only_missing:
            q += " WHERE potential_indications IS NULL"
        q += " ORDER BY created_at DESC"

        rows = await session.execute(sa_text(q))
        items = rows.fetchall()

        processed = 0
        for row in items:
            if limit and processed >= limit: break
            comb_id, rah_ids = row[0], list(row[1])
            try:
                ok = await process_row(session, comb_id, rah_ids)
                if ok:
                    await session.commit()
                    processed += 1
                    if processed % 10 == 0:
                        print(f"[backfill] processed {processed}")
            except Exception as e:
                await session.rollback()
                print(f"[backfill] {comb_id} failed: {e}")
            finally:
                await asyncio.sleep(min_interval)

        print(f"[backfill] done: {processed}")

def main():
    ap = argparse.ArgumentParser(description="Backfill potential_indications on combination rows.")
    ap.add_argument("--limit", type=int, help="Max rows", default=None)
    ap.add_argument("--rps", type=float, default=1.0, help="LLM calls per second")
    ap.add_argument("--only-missing", action="store_true", help="Only rows with NULL potential_indications")
    args = ap.parse_args()
    asyncio.run(run(args.limit, args.only_missing, args.rps))

if __name__ == "__main__":
    main()
