from sqlalchemy import BigInteger, Integer, Numeric, Text, TIMESTAMP, func, ForeignKey, Boolean
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from .db import Base

class PhysiologyProgram(Base):
    __tablename__ = "physiology_program"
    __table_args__ = {"schema": "rah_schema"}

    program_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sex: Mapped[str] = mapped_column(Text, nullable=False, default="unisex")

    items: Mapped[list["RahItemProgram"]] = relationship(back_populates="program")

class RahItem(Base):
    __tablename__ = "rah_item"
    __table_args__ = {"schema": "rah_schema"}

    rah_id: Mapped[float] = mapped_column(Numeric(5,2), primary_key=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    programs: Mapped[list["RahItemProgram"]] = relationship(back_populates="item", cascade="all, delete-orphan")

class RahItemProgram(Base):
    __tablename__ = "rah_item_program"
    __table_args__ = {"schema": "rah_schema"}

    rah_id: Mapped[float] = mapped_column(ForeignKey("rah_schema.rah_item.rah_id", ondelete="CASCADE"), primary_key=True)
    program_code: Mapped[int] = mapped_column(ForeignKey("rah_schema.physiology_program.program_code", ondelete="CASCADE"), primary_key=True)

    item: Mapped["RahItem"] = relationship(back_populates="programs")
    program: Mapped["PhysiologyProgram"] = relationship(back_populates="items")

class CorpusDoc(Base):
    __tablename__ = "corpus_doc"
    __table_args__ = {"schema": "rah_schema"}

    doc_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

class CorpusChunk(Base):
    __tablename__ = "corpus_chunk"
    __table_args__ = {"schema": "rah_schema"}

    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("rah_schema.corpus_doc.doc_id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

class UserAccount(Base):
    __tablename__ = "user_account"
    __table_args__ = {"schema": "rah_schema"}

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()"))
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_argon2: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
