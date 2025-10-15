# backend/app/db.py
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# ---- DB connection ----------------------------------------------------------
# Use your local Postgres 16 by default.
# Example: postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db>
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://rah:rahpw@host.docker.internal:5432/rah",
)

engine = create_async_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

Base = declarative_base()

# ---- App/AI config (used elsewhere) ----------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
GEN_MODEL = os.getenv("GEN_MODEL", "llama3.1:8b")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

# ---- FastAPI dependency -----------------------------------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
