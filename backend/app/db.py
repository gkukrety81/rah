import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_DSN = os.getenv("DB_DSN", "postgresql+asyncpg://rah:rahpw@host.docker.internal:5432/rah")

engine = create_async_engine(DB_DSN, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass
