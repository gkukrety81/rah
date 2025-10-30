import asyncio, json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text as sa_text
import os

DSN = os.getenv("DB_DSN")

async def main():
    eng = create_async_engine(DSN, future=True)
    async with eng.begin() as conn:
        await conn.execute(sa_text("""
                                   INSERT INTO rah_schema.rah_base_profiles (program_code, profile_text)
                                   SELECT DISTINCT CAST(ip.program_code AS int),
                                                   COALESCE(NULLIF(i.description,''), i.details)
                                   FROM rah_schema.rah_item i
                                            JOIN rah_schema.rah_item_program ip ON ip.rah_id = i.rah_id
                                       ON CONFLICT (program_code) DO NOTHING
                                   """))
    await eng.dispose()

if __name__ == "__main__":
    asyncio.run(main())
