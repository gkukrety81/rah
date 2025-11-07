# backend/app/scripts/harmonise_recommendations.py
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text
from app.db import get_session
from app.ai import _recommendations_from_text, _bullets

async def main():
    async for session in get_session():
        rows = await session.execute(sa_text("""
                                             SELECT case_id::text, recommendations
                                             FROM rah_schema.checkup_case
                                             """))
        for cid, rec in rows:
            if not rec:
                continue
            parsed = _recommendations_from_text(rec)
            bio = parsed.get("bioresonance", [])
            if not bio:
                continue

            # Rebuild clean text block
            new_block = "Rayonex Bioresonance:\n" + "\n".join(f"- {ln}" for ln in _bullets(bio)) + "\n"

            patched = rec
            if "Rayonex Bioresonance:" in rec:
                import re
                patched = re.sub(r"Rayonex Bioresonance:.*", new_block, rec, flags=re.DOTALL | re.IGNORECASE)
            else:
                patched = (rec.rstrip() + "\n\n" + new_block)

            await session.execute(
                sa_text("""
                        UPDATE rah_schema.checkup_case
                        SET recommendations = :patched
                        WHERE case_id = CAST(:cid AS uuid)
                        """),
                {"cid": cid, "patched": patched.strip()},
            )
        await session.commit()

if __name__ == "__main__":
    asyncio.run(main())
