# backend/app/scripts/backfill_bioresonance_recommendations.py
from __future__ import annotations

import asyncio
from typing import List

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.ai import _bioresonance_for_rah  # deterministic helper from ai.py


async def process_one(
        session: AsyncSession,
        combo_id: str,
        rah_ids: List[float],
        existing_reco: str | None,
) -> bool:
    """
    Append a Rayonex Bioresonance section to recommendations, if not already present.
    Returns True if an update was written.
    """
    existing = (existing_reco or "").strip()

    # If it already has Rayonex/bioresonance text, skip
    low = existing.lower()
    if "bioresonance" in low or "rayonex" in low:
        return False

    # Generate deterministic bioresonance bullets for this triad
    bio_lines = _bioresonance_for_rah(list(rah_ids or []))
    if not bio_lines:
        return False

    section_lines = ["Rayonex Bioresonance:"]
    section_lines.extend(f"- {line}" for line in bio_lines)
    section = "\n".join(section_lines)

    if existing:
        new_text = existing + "\n\n" + section
    else:
        # If there is no existing recommendation text, just store the bioresonance section
        new_text = section

    await session.execute(
        sa_text(
            """
            UPDATE rah_schema.rah_combination_profiles
            SET recommendations = :rec
            WHERE combination_id = CAST(:cid AS uuid)
            """
        ),
        {"rec": new_text, "cid": combo_id},
    )
    return True


async def main() -> None:
    async with SessionLocal() as session:  # type: ignore[arg-type]
        res = await session.execute(
            sa_text(
                """
                SELECT combination_id::text,
                    rah_ids,
                       recommendations
                FROM rah_schema.rah_combination_profiles
                ORDER BY combination_id
                """
            )
        )
        rows = res.fetchall()
        total = len(rows)
        print(f"[bioresonance] Found {total} combinations")

        updated = 0
        for idx, (combo_id, rah_ids, reco) in enumerate(rows, start=1):
            try:
                changed = await process_one(session, combo_id, list(rah_ids or []), reco)
                if changed:
                    updated += 1
                    await session.commit()
                if idx % 50 == 0:
                    print(f"[bioresonance] processed {idx}/{total}, updated={updated}")
            except Exception as e:
                await session.rollback()
                print(f"[bioresonance] ERROR on {combo_id}: {e!r}")

        print(f"[bioresonance] done. Updated {updated} rows out of {total}")


if __name__ == "__main__":
    asyncio.run(main())
