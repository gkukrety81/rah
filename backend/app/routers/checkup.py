# backend/app/routers/checkup.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.ai import run_analysis_sections  # your LLM section builder
import re, json

def _clean_blurb(text: str) -> str:
    if not text:
        return ""

    # If the model dumped JSON inline, try to cut it out.
    # crude: remove a block that starts with { and ends with }
    cleaned = re.sub(r"\n?\*\*?JSON\*\*?.*$", "", text, flags=re.IGNORECASE | re.DOTALL)

    try:
        # also handle the case where the entire blurb is JSON
        obj = json.loads(text)
        if isinstance(obj, dict) and "analysis" in obj:
            return str(obj["analysis"]).strip()
    except Exception:
        pass

    return cleaned.strip()

router = APIRouter(prefix="/checkup", tags=["checkup"])


# ----------------------------- Pydantic -----------------------------

class StartIn(BaseModel):
    rah_ids: List[float] = Field(min_items=3, max_items=3)

class StartOut(BaseModel):
    ok: bool = True
    case_id: str
    rah_ids: List[float]
    combination_title: Optional[str] = ""
    analysis_blurb: Optional[str] = ""
    questions: List[Dict[str, Any]] = []
    recommendations: Optional[str] = ""
    source: str  # "db" or "ai"

class AnswersIn(BaseModel):
    case_id: str
    selected_ids: List[str] = []
    notes: str = ""

class AnswersOut(BaseModel):
    ok: bool = True

class SaveAnswersIn(BaseModel):
    case_id: str
    selected: List[str] = []
    notes: Optional[str] = ""

class AnalyzeIn(BaseModel):
    case_id: str

class AnalyzeOut(BaseModel):
    case_id: str
    sections: Dict[str, Any]
    markdown: str

# ------------------------------ Utils ------------------------------

def _triad_key(ids: List[float]) -> str:
    """Canonical key for 3 RAH IDs, e.g. '30.00,50.00,76.00'."""
    s = [f"{float(x):.2f}" for x in sorted(float(v) for v in ids)]
    return ",".join(s)

# ------------------------------ Routes -----------------------------

@router.post("/start", response_model=StartOut)
async def start_checkup(payload: StartIn, session: AsyncSession = Depends(get_session)):
    ids_sorted = sorted(float(x) for x in payload.rah_ids)
    key = _triad_key(ids_sorted)

    # 1) Try to fetch combination from rah_combination_profiles
    row = await session.execute(sa_text("""
                                        SELECT combination_id::text,
                                            rah_ids,
                                               combination_title,
                                               analysis,
                                               potential_indications,
                                               recommendations
                                        FROM rah_schema.rah_combination_profiles
                                        WHERE combo_key = :k
                                            LIMIT 1
                                        """), {"k": key})
    comb = row.first()

    # 2) Persist a checkup_case row (needed for analyze flow)
    if comb:
        # known DB-backed combination
        ins = await session.execute(sa_text("""
                                            INSERT INTO rah_schema.checkup_case
                                            (rah_ids, combination, analysis_blurb, questions, recommendations, source)
                                            VALUES
                                                (:rah, :comb, :blurb, '[]'::jsonb, :reco, 'db')
                                                RETURNING case_id::text
                                            """), {
                                        "rah": ids_sorted,
                                        "comb": str(comb[2] or ""),
                                        "blurb": str(comb[3] or ""),
                                        "reco": str(comb[5] or ""),
                                    })
        case_id = ins.scalar_one()
        await session.commit()

        return StartOut(
            case_id=case_id,
            rah_ids=ids_sorted,
            combination_title=str(comb[2] or ""),
            analysis_blurb=str(comb[3] or ""),
            questions=[],  # we can fill from comb[4] later if you want
            recommendations=str(comb[5] or ""),
            source="db",
        )

    # 3) Fallback: create a case without DB combo (UI still works, analyze will be AI)
    ins = await session.execute(sa_text("""
                                        INSERT INTO rah_schema.checkup_case
                                        (rah_ids, combination, analysis_blurb, questions, recommendations, source)
                                        VALUES
                                            (:rah, '', '', '[]'::jsonb, '', 'ai')
                                            RETURNING case_id::text
                                        """), {"rah": ids_sorted})
    case_id = ins.scalar_one()
    await session.commit()

    return StartOut(
        case_id=case_id,
        rah_ids=ids_sorted,
        combination_title="",
        analysis_blurb="",
        questions=[],
        recommendations="",
        source="ai",
    )


@router.post("/checkup/answers")
async def save_answers(payload: SaveAnswersIn):
    # Minimal validation
    cid = (payload.case_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="case_id required")

    selected = payload.selected or []
    notes = (payload.notes or "").strip()

    async with SessionLocal() as session:
        # Ensure the case exists (optional but helpful)
        row = await session.execute(
            sa_text("""
                    SELECT 1 FROM rah_schema.checkup_case
                    WHERE case_id = :cid::uuid
                LIMIT 1
                    """),
            {"cid": cid},
        )
        if row.first() is None:
            # Mirrors what your analyze endpoint does
            raise HTTPException(status_code=404, detail="Unknown case_id")

        # Properly use ONLY named parameters
        await session.execute(
            sa_text("""
                    INSERT INTO rah_schema.checkup_answers (case_id, selected_ids, notes)
                    VALUES (:cid::uuid, :sel::text[], :notes)
                        ON CONFLICT (case_id) DO UPDATE
                                                     SET selected_ids = EXCLUDED.selected_ids,
                                                     notes        = EXCLUDED.notes
                    """),
            {
                "cid": cid,
                "sel": selected,   # list[str] -> text[] is fine with :sel::text[]
                "notes": notes,
            },
        )
        await session.commit()

    return {"ok": True}


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    # 1) fetch case (only case_id matters; answers are optional)
    row = await session.execute(sa_text("""
                                        SELECT case_id::text,
                                            rah_ids,
                                               COALESCE(combination, '') AS combination,
                                               COALESCE(analysis_blurb, '') AS analysis_blurb,
                                               COALESCE(recommendations, '') AS recommendations
                                        FROM rah_schema.checkup_case
                                        WHERE case_id::text = :cid
         LIMIT 1
                                        """), {"cid": payload.case_id})
    case = row.first()
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    # 2) optional answers (empty is valid)
    ans = await session.execute(sa_text("""
                                        SELECT COALESCE(selected_ids, ARRAY[]::text[]) AS selected_ids,
                                               COALESCE(notes, '') AS notes
                                        FROM rah_schema.checkup_answers
                                        WHERE case_id::text = :cid
         LIMIT 1
                                        """), {"cid": payload.case_id})
    arow = ans.first()
    selected_ids = list(arow[0]) if arow else []
    notes = str(arow[1] or "") if arow else ""

    # 3) AI section builder
    try:
        sections = await run_analysis_sections(
            rah_ids=[float(x) for x in case[1]],
            combination=str(case[2] or ""),
            analysis_blurb=str(case[3] or ""),
            selected_ids=selected_ids,
            notes=notes,
            recommendations=str(case[4] or ""),
        )
    except Exception:
        # keep the endpoint resilient
        sections = {
            "correlated_systems": [],
            "indications": [],
            "note_synthesis": "",
            "diagnostic_summary": "",
            "recommendations": {
                "lifestyle": [],
                "nutritional": [],
                "emotional": [],
                "bioresonance": [],
                "follow_up": [],
            },
        }

    # 4) pretty markdown
    def bullets(items):
        return "\n".join([f"- {x}" for x in (items or [])])

    rec = sections.get("recommendations", {}) or {}
    md = f"""# RAI Analysis

## Correlated Systems Analysis
{bullets(sections.get("correlated_systems", []))}

## Indication Interpretation
{bullets(sections.get("indications", []))}

## Note Synthesis
{sections.get("note_synthesis", "")}

## 200-Word Diagnostic Summary
{sections.get("diagnostic_summary", "")}

## Tailored Recommendations
**Lifestyle**  
{bullets(rec.get("lifestyle", []))}

**Nutritional**  
{bullets(rec.get("nutritional", []))}

**Emotional**  
{bullets(rec.get("emotional", []))}

**Rayonex Bioresonance**  
{bullets(rec.get("bioresonance", []))}

**Follow-Up**  
{bullets(rec.get("follow_up", []))}
""".strip()

    return AnalyzeOut(case_id=payload.case_id, sections=sections, markdown=md)
