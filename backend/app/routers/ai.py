# app/routers/ai.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text
from sqlalchemy import update, select
import re

from ..models import RahItem
from ..db import get_session, EMBED_DIM
from ..ollama_client import ollama_embed, ollama_generate, to_pgvector_literal
from ..embedding_refresh import refresh_embeddings as refresh_embeddings_helper

router = APIRouter(prefix="/ai", tags=["ai"])
ai_router = APIRouter(prefix="/ai", tags=["ai"])

class TranslateIn(BaseModel):
    text: str
    target_lang: str = "de"  # ISO-ish tag, default German

class TranslateOut(BaseModel):
    text: str
    lang: str

_TRANSLATE_SYS = (
    "You are a precise medical translator. Translate the user content to the target language. "
    "Preserve markdown structure, headings, bullets, and clinical tone. Do not add extra commentary."
)

@ai_router.post("/translate", response_model=TranslateOut)
async def translate(inb: TranslateIn) -> TranslateOut:
    user = f"Target language: {inb.target_lang}\n\nContent:\n{inb.text}"
    out = await ollama_generate(user, system=_TRANSLATE_SYS)
    return TranslateOut(text=out.strip(), lang=inb.target_lang)

class AnalyzeIn(BaseModel):
    prompt: str
    top_k: int = 5


@router.post("/refresh-embeddings")
async def refresh_embeddings(all: bool = False, session: AsyncSession = Depends(get_session)):
    """
    Rebuild (or create) embeddings for all RAH items.
    If `all` is False, only items missing embeddings or recently updated are processed.
    """
    # Ensure table exists (idempotent)
    await session.execute(sa_text(f"""
        CREATE TABLE IF NOT EXISTS rah_schema.rah_embeddings (
            rah_id      numeric(5,2) PRIMARY KEY,
            source_text text NOT NULL,
            embedding   vector({EMBED_DIM})
        );
    """))
    await session.commit()

    updated = await refresh_embeddings_helper(session, refresh_all=all)
    return {"updated": updated}


@router.post("/analyze")
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Empty prompt")
    k = max(1, min(payload.top_k, 20))

    # Optional: hint likely physiology programs via LLM
    sys = (
        "You map clinical complaints to likely physiology program codes. "
        "Programs are integers like 30,32,34,36,38,40,42,44,46,48,50,52,54,56,58,62,64,66,68,72,75,76. "
        "Return a short JSON array of integers."
    )
    hint = await ollama_generate(
        f"Symptoms: {prompt}\nReturn JSON array only, e.g. [58,40]",
        system=sys
    )

    allowed = {30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 62, 64, 66, 68, 72, 75, 76}
    # Grab two-digit numbers, filter to allowed, de-dup and cap to 5
    codes = [int(x) for x in re.findall(r"\d{2}", hint) if int(x) in allowed]
    codes = list(dict.fromkeys(codes))[:5]

    # Embed the query
    q = await ollama_embed(prompt)
    q_str = to_pgvector_literal(q)

    # Build WHERE safely (avoid ANY(:codes) to keep named params consistent)
    params = {"q": q_str, "k": k}
    if codes:
        placeholders = []
        for idx, code in enumerate(codes):
            key = f"c{idx}"
            placeholders.append(f":{key}")
            params[key] = int(code)
        where_clause = f"WHERE ip.program_code IN ({', '.join(placeholders)})"
    else:
        where_clause = ""

    res = await session.execute(sa_text(f"""
        SELECT i.rah_id,
               i.details,
               i.category,
               1 - (e.embedding <=> CAST(:q AS vector)) AS similarity,
               ip.program_code,
               p.name AS program_name
        FROM rah_schema.rah_embeddings e
        JOIN rah_schema.rah_item i           ON i.rah_id = e.rah_id
        JOIN rah_schema.rah_item_program ip  ON ip.rah_id = i.rah_id
        JOIN rah_schema.physiology_program p ON p.program_code = ip.program_code
        {where_clause}
        ORDER BY e.embedding <=> CAST(:q AS vector)
        LIMIT :k
    """), params)

    rows = [
        {
            "rah_id": float(r[0]),
            "details": r[1],
            "category": r[2],
            "similarity": float(r[3]),
            "program_code": int(r[4]),
            "program_name": r[5],
        }
        for r in res.fetchall()
    ]

    summary = await ollama_generate(
        "Symptoms: " + prompt + "\nTop candidates: " +
        ", ".join(f"{x['rah_id']} {x['details']} ({x['program_name']})" for x in rows[:5]) +
        "\nExplain briefly why the top 3 are relevant (2-3 lines)."
    )

    return {"program_hints": codes, "matches": rows, "explanation": summary}

@router.post("/generate-description/{rah_id}")
async def generate_description(rah_id: float, session: AsyncSession = Depends(get_session)):
    r = await session.execute(select(RahItem).where(RahItem.rah_id == rah_id))
    item = r.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="RAH ID not found")

    prompt = (
        "Write a structured medical narrative (~1000 words) for the following RAH item. "
        "Use clear sections: Overview, Physiology/Mechanism, Clinical Presentation, "
        "Differential Considerations, Assessment, and Supportive/Therapeutic Notes. "
        f"\n\nName: {item.details}\nCategory: {item.category}\n"
    )
    text = await ollama_generate(prompt)

    await session.execute(
        update(RahItem)
        .where(RahItem.rah_id == rah_id)
        .values(description=text)
    )
    await session.commit()
    return {"ok": True}
