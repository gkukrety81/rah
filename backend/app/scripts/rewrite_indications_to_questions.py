# backend/app/scripts/rewrite_indications_to_questions.py
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal  # same thing you used in earlier scripts
from app.ai import rewrite_indications_to_questions


async def _needs_rewrite(pi: Any) -> bool:
    """
    Decide if a potential_indications blob still needs rewriting.
    We skip rows where ALL strings already contain a '?'.
    """
    if not isinstance(pi, dict):
        return True

    any_items = False
    for items in pi.values():
        if not isinstance(items, list):
            continue
        for s in items:
            any_items = True
            if "?" not in str(s):
                return True

    # If there were zero items at all, we consider it "no work"
    return False if any_items else True


async def process_one(session: AsyncSession, combo_id: str, pi: Dict[str, Any]) -> None:
    new_pi = await rewrite_indications_to_questions(pi)

    await session.execute(
        sa_text(
            """
            UPDATE rah_schema.rah_combination_profiles
            SET potential_indications = CAST(:pi AS jsonb),
                updated_at            = now()
            WHERE combination_id = CAST(:cid AS uuid)
            """
        ),
        {"pi": json.dumps(new_pi), "cid": combo_id},
    )


async def main() -> None:
    async with SessionLocal() as session:  # type: ignore[arg-type]
        res = await session.execute(
            sa_text(
                """
                SELECT combination_id::text, potential_indications
                FROM rah_schema.rah_combination_profiles
                WHERE potential_indications IS NOT NULL
                ORDER BY combination_id
                """
            )
        )
        rows = res.fetchall()

        total = len(rows)
        print(f"[rewrite] Found {total} combinations with potential_indications")

        count_todo = 0
        for combo_id, pi in rows:
            if await _needs_rewrite(pi):
                count_todo += 1
        print(f"[rewrite] {count_todo} combinations need rewrite")

        if count_todo == 0:
            print("[rewrite] nothing to do")
            return

        # simple sequential loop (1000 rows is fine)
        done = 0
        for combo_id, pi in rows:
            if not await _needs_rewrite(pi):
                continue

            done += 1
            print(f"[rewrite] {done}/{count_todo} -> {combo_id}")
            try:
                await process_one(session, combo_id, pi)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"[rewrite] ERROR on {combo_id}: {e!r}")

        print("[rewrite] completed")


if __name__ == "__main__":
    asyncio.run(main())
