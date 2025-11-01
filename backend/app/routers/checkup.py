from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
import re
import json

from app.db import get_session, SessionLocal
from app.ai import run_analysis_sections  # ensure this exists

router = APIRouter(prefix="/checkup", tags=["checkup"])


# ----------------------------- Helpers -----------------------------

def _clean_blurb(text: str) -> str:
    if not text:
        return ""
    # Remove trailing JSON or debug artefact
    cleaned = re.sub(r"\n?\*\*?JSON\*\*?.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "analysis" in obj:
            return str(obj["analysis"]).strip()
    except Exception:
        pass
    return cleaned.strip()


def _triad_key(ids: List[float]) -> str:
    s = [f"{float(x):.2f}" for x in sorted(float(v) for v in ids)]
    return ",".join(s)


# ----------------------------- Models -----------------------------

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


# ----------------------------- Routes -----------------------------

@router.post("/start", response_model=StartOut)
async def start_checkup(payload: StartIn, session: AsyncSession = Depends(get_session)):
    ids_sorted = sorted(float(x) for x in payload.rah_ids)
    key = _triad_key(ids_sorted)

    row = await session.execute(
        sa_text("""
                SELECT combination_id::text, rah_ids, combination_title, analysis,
                       potential_indications, recommendations
                FROM rah_schema.rah_combination_profiles
                WHERE combo_key = :k
                    LIMIT 1
                """),
        {"k": key},
    )
    comb = row.first()

    if comb:
        # Build questions from potential_indications JSON
        questions: List[Dict[str, Any]] = []
        try:
            pi = comb[4] or {}
            for group in ("Physical", "Psychological/Emotional", "Functional"):
                items = list(pi.get(group, []) or [])
                for i, text_item in enumerate(items):
                    qid = f"{group[:3].upper()}-{i+1}"
                    questions.append({"id": qid, "text": text_item, "group": group})
        except Exception:
            questions = []

        ins = await session.execute(
            sa_text("""
                    INSERT INTO rah_schema.checkup_case
                    (rah_ids, combination, analysis_blurb, questions, recommendations, source)
                    VALUES (:rah, :comb, :blurb, CAST(:qs AS jsonb), :reco, 'db')
                        RETURNING case_id::text
                    """),
            {
                "rah": ids_sorted,
                "comb": str(comb[2] or ""),
                "blurb": _clean_blurb(str(comb[3] or "")),
                "qs": json.dumps(questions),
                "reco": str(comb[5] or ""),
            },
        )
        case_id = ins.scalar_one()
        await session.commit()

        return StartOut(
            case_id=case_id,
            rah_ids=ids_sorted,
            combination_title=str(comb[2] or ""),
            analysis_blurb=_clean_blurb(str(comb[3] or "")),
            questions=questions,
            recommendations=str(comb[5] or ""),
            source="db",
        )

    # fallback: AI path
    ins = await session.execute(
        sa_text("""
                INSERT INTO rah_schema.checkup_case
                (rah_ids, combination, analysis_blurb, questions, recommendations, source)
                VALUES (:rah, '', '', '[]'::jsonb, '', 'ai')
                    RETURNING case_id::text
                """),
        {"rah": ids_sorted},
    )
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


@router.post("/answers")
async def save_answers(payload: SaveAnswersIn):
    cid = (payload.case_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="case_id required")

    selected = payload.selected or []
    notes = (payload.notes or "").strip()

    async with SessionLocal() as session:
        exists = await session.execute(
            sa_text("""
                    SELECT 1 FROM rah_schema.checkup_case
                    WHERE case_id = :cid::uuid
                LIMIT 1
                    """),
            {"cid": cid},
        )
        if exists.first() is None:
            raise HTTPException(status_code=404, detail="Unknown case_id")

        await session.execute(
            sa_text("""
                    INSERT INTO rah_schema.checkup_answers (case_id, selected_ids, notes)
                    VALUES (:cid::uuid, :sel::text[], :notes)
                        ON CONFLICT (case_id)
                  DO UPDATE SET
                        selected_ids = EXCLUDED.selected_ids,
                                                 notes = EXCLUDED.notes
                    """),
            {"cid": cid, "sel": selected, "notes": notes},
        )
        await session.commit()

    return {"ok": True}


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    case_q = await session.execute(
        sa_text("""
                SELECT case_id::text, rah_ids,
                       COALESCE(combination, '') AS combination,
                       COALESCE(analysis_blurb, '') AS analysis_blurb,
                       COALESCE(recommendations, '') AS recommendations
                FROM rah_schema.checkup_case
                WHERE case_id::text = :cid
            LIMIT 1
                """),
        {"cid": payload.case_id},
    )
    case = case_q.first()
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    ans_q = await session.execute(
        sa_text("""
                SELECT COALESCE(selected_ids, ARRAY[]::text[]) AS selected_ids,
                       COALESCE(notes, '') AS notes
                FROM rah_schema.checkup_answers
                WHERE case_id::text = :cid
            LIMIT 1
                """),
        {"cid": payload.case_id},
    )
    ans = ans_q.first()
    selected_ids = list(ans[0]) if ans else []
    notes = str(ans[1] or "") if ans else ""

    try:
        sections = await run_analysis_sections(
            rah_ids=[float(x) for x in case[1]],
            combination=str(case[2] or ""),
            analysis_blurb=_clean_blurb(str(case[3] or "")),
            selected_ids=selected_ids,
            notes=notes,
            recommendations=str(case[4] or ""),
        )
    except Exception:
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

    def bullets(items): return "\n".join([f"- {x}" for x in (items or [])])
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

    # Persist result for history
    await session.execute(
        sa_text("""
                INSERT INTO rah_schema.checkup_result (case_id, sections, markdown)
                VALUES (:cid::uuid, CAST(:sec AS jsonb), :md)
                    ON CONFLICT (case_id)
              DO UPDATE SET sections = EXCLUDED.sections,
                                         markdown = EXCLUDED.markdown
                """),
        {"cid": payload.case_id, "sec": json.dumps(sections), "md": md},
    )
    await session.commit()

    return AnalyzeOut(case_id=payload.case_id, sections=sections, markdown=md)
