import asyncio, os
from .db import engine

async def run_init():
    sql_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    async with engine.begin() as conn:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            await conn.exec_driver_sql(stmt + ";")
    print("Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(run_init())