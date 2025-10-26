# backend/app/scripts/backfill_descriptions.py
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text

from ..db import SessionLocal, EMBED_DIM
from ..ollama_client import ollama_generate, ollama_embed, to_pgvector_literal

WORDS = 1000  # target length

PROMPT_TEMPLATE = """
You are a clinical writing assistant. Write a structured medical-style narrative (~{words} words)
for the following RAH item. Avoid diagnoses; focus on physiology, common manifestations,
related systems, typical client complaints, and supportive lifestyle considerations.

Return plain prose ONLY (no headings, no markdown).

RAH ID: {rah_id:.2f}
Title: {title}
Category: {category}
"""

async def main():
    async with SessionLocal() as session:  # type: AsyncSession
        # Ensure embeddings table exists
        await session.execute(sa_text(f"""
            CREATE TABLE IF NOT EXISTS rah_schema.rah_embeddings (
              rah_id      numeric(5,2) PRIMARY KEY,
              source_text text NOT NULL,
              embedding   vector({EMBED_DIM})
            );
        """))
        await session.commit()

        # Items missing description
        res = await session.execute(sa_text("""
                                            SELECT rah_id, details, category
                                            FROM rah_schema.rah_item
                                            WHERE (description IS NULL OR description = '')
                                            ORDER BY rah_id
                                            """))
        rows = res.fetchall()
        print(f"[backfill] items to generate: {len(rows)}")

        for rah_id, details, category in rows:
            rid = float(rah_id)
            title = details or ""
            cat = category or ""
            print(f" - generating {rid:.2f} …")

            prompt = PROMPT_TEMPLATE.format(rah_id=rid, title=title, category=cat, words=WORDS)
            narrative = await ollama_generate(
                prompt,
                system="Write clear, evidence-informed prose. No markdown; no lists."
            )

            # Update rah_item
            await session.execute(
                sa_text("""UPDATE rah_schema.rah_item
                           SET description = :d, updated_at = NOW()
                           WHERE rah_id = :id"""),
                {"d": narrative, "id": rah_id},
            )

            # Embed + upsert
            vec = await ollama_embed(narrative)
            vec_str = to_pgvector_literal(vec)

            await session.execute(
                sa_text("""
                        INSERT INTO rah_schema.rah_embeddings (rah_id, source_text, embedding)
                        VALUES (:id, :src, CAST(:vec AS vector))
                            ON CONFLICT (rah_id) DO UPDATE
                                                        SET source_text = EXCLUDED.source_text,
                                                        embedding   = EXCLUDED.embedding
                        """),
                {"id": rah_id, "src": narrative, "vec": vec_str},
            )

            await session.commit()

    print("[backfill] done.")

if __name__ == "__main__":
    asyncio.run(main())
