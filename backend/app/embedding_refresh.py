# app/embedding_refresh.py
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from .ollama_client import ollama_embed, to_pgvector_literal
from .db import EMBED_DIM

async def refresh_embeddings(session: AsyncSession, refresh_all: bool = False) -> int:
    await session.execute(sa_text(f"""
        CREATE TABLE IF NOT EXISTS rah_schema.rah_embeddings (
            rah_id      numeric(5,2) PRIMARY KEY,
            source_text text NOT NULL,
            embedding   vector({EMBED_DIM})
        );
    """))
    await session.execute(sa_text("""
                                  CREATE INDEX IF NOT EXISTS rah_embeddings_idx
                                      ON rah_schema.rah_embeddings USING ivfflat (embedding);
                                  """))
    await session.commit()

    where = "" if refresh_all else """
        WHERE e.rah_id IS NULL
           OR i.updated_at > NOW() - interval '1 day'
    """
    result = await session.execute(sa_text(f"""
        SELECT i.rah_id, COALESCE(NULLIF(i.description,''), i.details) AS src
        FROM rah_schema.rah_item i
        LEFT JOIN rah_schema.rah_embeddings e ON e.rah_id = i.rah_id
        {where}
        ORDER BY i.rah_id
    """))
    rows = result.fetchall()

    count = 0
    for rah_id, src in rows:
        if not src:
            continue
        vec = await ollama_embed(src)
        vec_str = to_pgvector_literal(vec)
        await session.execute(sa_text("""
                                      INSERT INTO rah_schema.rah_embeddings (rah_id, source_text, embedding)
                                      VALUES (:id, :src, CAST(:vec AS vector))
                                          ON CONFLICT (rah_id) DO UPDATE
                                                                      SET source_text = EXCLUDED.source_text,
                                                                      embedding   = EXCLUDED.embedding
                                      """), {"id": float(rah_id), "src": src, "vec": vec_str})
        count += 1

    await session.commit()
    return count
