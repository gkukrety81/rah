# app/routers/checkup.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text, select
from ..db import get_session
from ..models import RahItem
from ..ollama_client import ollama_generate

router = APIRouter(prefix="/checkup", tags=["checkup"])

# ---------- Pydantic ----------
class StartIn(BaseModel):
    rah_ids: List[float] = Field(..., min_items=3, max_items=3)

class Question(BaseModel):
    id: str
    text: str
    group: str  # Physical | Psychological/Emotional | Functional

class StartOut(BaseModel):
    case_id: str
    rah_ids: List[float]
    combination_title: str
    analysis_blurb: str
    questions: List[Question]
    recommendations: Optional[str] = None
    source: str  # "db" or "ai"

class AnswersIn(BaseModel):
    case_id: str
    selected: List[str] = []
    notes: Optional[str] = None

class AnalyzeIn(BaseModel):
    case_id: str

class AnalyzeOut(BaseModel):
    case_id: str
    sections: Dict[str, Any]
    markdown: str

# ---------- Prompts ----------
COMBO_TITLE_SYS = (
    "You are given descriptions of three physiology IDs from a knowledge base. "
    "1) Propose a concise 'Combination:' line (max ~140 chars) that names the overlapping systems. "
    "2) Provide a 1-2 sentence neutral 'Analysis' blurb describing likely shared dysfunction."
)
QUESTION_SYS = (
    "From the three physiology descriptions, produce a short YES/NO questionnaire that a practitioner can ask. "
    "Return 8–12 crisp items grouped across Physical, Psychological/Emotional, and Functional. "
    "Output as JSON array with objects: {id, text, group} where group is one of "
    "'Physical','Psychological/Emotional','Functional'. IDs should be stable, kebab-case."
)

ANALYZE_SYS = (
    "You are a clinical summarizer. Using selected YES/NO indicators and notes, "
    "generate a concise professional analysis with headings exactly as below:\n"
    "1) Correlated Systems Analysis (3 bullet lines)\n"
    "2) Indication Interpretation (3 bullet lines)\n"
    "3) Note Synthesis (1-2 sentences)\n"
    "4) 200-Word Diagnostic Summary (one paragraph ~200 words)\n"
    "5) Tailored Recommendations (Lifestyle / Nutritional / Emotional / Rayonex Bioresonance / Follow-Up bullets)\n"
    "Return a JSON object with keys: correlated_systems, indications, note_synthesis, diagnostic_summary, "
    "recommendations (with lifestyle, nutritional, emotional, bioresonance, follow_up arrays)."
)

CREATE_SQL = """
             CREATE TABLE IF NOT EXISTS rah_schema.checkup_case(
                                                                   case_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                 rah_ids        numeric(5,2)[] NOT NULL,
                 combination    text,
                 analysis_blurb text,
                 questions      jsonb,
                 answers        jsonb,
                 notes          text,
                 results        jsonb,
                 recommendations text,
                 source         text,
                 created_at     timestamptz NOT NULL DEFAULT now()
                 ); \
             """

async def _ensure_table_runtime(session: AsyncSession):
    await session.execute(sa_text(CREATE_SQL))
    await session.commit()

async def _fetch_rah_descriptions(session: AsyncSession, rah_ids: List[float]) -> Dict[float, str]:
    q = await session.execute(
        select(RahItem.rah_id, RahItem.details, RahItem.description)
        .where(RahItem.rah_id.in_(rah_ids))
    )
    by_id: Dict[float, str] = {}
    for rid, details, desc in q.all():
        by_id[float(rid)] = (desc or "").strip() or (details or "").strip()
    return by_id

def _norm_key(ids: List[float]) -> str:
    return ",".join(f"{float(x):.2f}" for x in sorted(ids))

async def _lookup_combo_row(session: AsyncSession, rah_ids: List[float]) -> Optional[dict]:
    # Your trigger populates combo_key as array_to_string(rah_ids, ',')
    key = _norm_key(rah_ids)
    r = await session.execute(sa_text("""
                                      SELECT combination_title, analysis, potential_indications, recommendations
                                      FROM rah_schema.rah_combination_profiles
                                      WHERE combo_key = :k
                                          LIMIT 1
                                      """), {"k": key})
    row = r.first()
    if not row:
        return None
    return {
        "combination_title": row[0] or "Combination",
        "analysis": row[1] or "",
        "potential_indications": row[2] or {},
        "recommendations": row[3] or None,
    }

# ---------- Endpoints ----------

@router.post("/start", response_model=StartOut)
async def start(payload: StartIn, session: AsyncSession = Depends(get_session)):
    await _ensure_table_runtime(session)

    if len(payload.rah_ids) != 3:
        raise HTTPException(400, "Exactly 3 RAH IDs are required.")

    # Prefer DB combination (Phase 2)
    db_combo = await _lookup_combo_row(session, payload.rah_ids)

    questions: List[Question] = []
    source = "db"

    if db_combo:
        # Convert grouped potential_indications -> question objects
        pi = db_combo.get("potential_indications") or {}
        def add_group(gname: str):
            for i, text in enumerate(pi.get(gname, []) or []):
                qid = f"{gname.lower().replace(' ', '-')}-{i+1}"
                questions.append(Question(id=qid, text=str(text), group=gname))
        add_group("Physical")
        add_group("Psychological/Emotional")
        add_group("Functional")

        # Create case persisted from cached triad
        import json
        row = await session.execute(sa_text("""
                                            INSERT INTO rah_schema.checkup_case(rah_ids, combination, analysis_blurb, questions, recommendations, source)
                                            VALUES (:rah_ids, :comb, :blurb, CAST(:qs AS jsonb), :rec, :src)
                                                RETURNING case_id::text;
                                            """), {
                                        "rah_ids": payload.rah_ids,
                                        "comb": db_combo["combination_title"],
                                        "blurb": db_combo["analysis"],
                                        "qs": json.dumps([q.dict() for q in questions]),
                                        "rec": db_combo.get("recommendations"),
                                        "src": source
                                    })
        case_id = row.scalar_one()
        return StartOut(
            case_id=case_id,
            rah_ids=payload.rah_ids,
            combination_title=db_combo["combination_title"],
            analysis_blurb=db_combo["analysis"],
            questions=questions,
            recommendations=db_combo.get("recommendations"),
            source=source
        )

    # Fall back to AI dynamic (unchanged logic)
    by_id = await _fetch_rah_descriptions(session, payload.rah_ids)
    if len(by_id) < 3:
        missing = [x for x in payload.rah_ids if x not in by_id]
        raise HTTPException(400, f"Unknown RAH IDs: {missing}")
    context = "\n\n".join([f"RAH {rid:.2f}:\n{by_id[rid]}" for rid in payload.rah_ids])

    combo = await ollama_generate(
        f"Descriptions from three RAH items:\n\n{context}\n\n"
        "Return two lines labeled exactly:\n"
        "Combination: <short title>\n"
        "Analysis: <1-2 sentence blurb>",
        system=COMBO_TITLE_SYS
    )
    combo_title, blurb = "", ""
    for line in combo.splitlines():
        if line.lower().startswith("combination:"):
            combo_title = line.split(":",1)[1].strip()
        if line.lower().startswith("analysis:"):
            blurb = line.split(":",1)[1].strip()

    qjson = await ollama_generate(
        f"Descriptions from three RAH items:\n\n{context}\n\n"
        "Produce questionnaire JSON now.",
        system=QUESTION_SYS
    )
    import json
    try:
        raw = json.loads(qjson)
        for q in raw:
            if isinstance(q, dict) and {"id","text","group"} <= set(q.keys()):
                questions.append(Question(id=str(q["id"]), text=str(q["text"]), group=str(q["group"])))
    except Exception:
        pass

    source = "ai"
    row = await session.execute(sa_text("""
                                        INSERT INTO rah_schema.checkup_case(rah_ids, combination, analysis_blurb, questions, source)
                                        VALUES (:rah_ids, :comb, :blurb, CAST(:qs AS jsonb), :src)
                                            RETURNING case_id::text;
                                        """), {"rah_ids": payload.rah_ids,
                                               "comb": combo_title or "Combination",
                                               "blurb": blurb or "",
                                               "qs": json.dumps([q.dict() for q in questions]),
                                               "src": source})
    case_id = row.scalar_one()

    return StartOut(
        case_id=case_id,
        rah_ids=payload.rah_ids,
        combination_title=combo_title or "Combination",
        analysis_blurb=blurb or "",
        questions=questions,
        recommendations=None,
        source=source
    )

@router.post("/answers")
async def save_answers(payload: AnswersIn, session: AsyncSession = Depends(get_session)):
    import json
    await _ensure_table_runtime(session)
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_case
                                  SET answers = CAST(:answers AS jsonb),
                                      notes   = :notes
                                  WHERE case_id = :cid
                                  """), {"answers": json.dumps(payload.selected or []),
                                         "notes": payload.notes or "",
                                         "cid": payload.case_id})
    await session.commit()
    return {"ok": True}

@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    await _ensure_table_runtime(session)
    res = await session.execute(sa_text("""
                                        SELECT case_id::text, rah_ids, combination, analysis_blurb, questions, answers, notes, recommendations
                                        FROM rah_schema.checkup_case
                                        WHERE case_id = :cid
                                        """), {"cid": payload.case_id})
    row = res.first()
    if not row:
        raise HTTPException(404, "Unknown case_id")
    case_id, rah_ids, combination, blurb, questions_json, answers_json, notes, recommendations = row

    import json
    questions = questions_json or []
    selected_ids = set(answers_json or [])
    picked = [q for q in questions if q.get("id") in selected_ids]

    # Build AI request exactly as before
    user_prompt = (
            f"Combination: {combination}\n"
            f"Short analysis: {blurb}\n\n"
            f"Selected indicators (YES):\n"
            + "\n".join([f"- [{q.get('group')}] {q.get('text')}" for q in picked]) + "\n\n"
                                                                                     f"Practitioner notes:\n{notes or '(none)'}\n\n"
                                                                                     f"Return JSON only per instructions."
    )
    raw = await ollama_generate(user_prompt, system=ANALYZE_SYS)
    try:
        sections = json.loads(raw) or {}
    except Exception:
        sections = {
            "correlated_systems": [], "indications": [], "note_synthesis": "",
            "diagnostic_summary": raw.strip(),
            "recommendations": {"lifestyle": [], "nutritional": [], "emotional": [], "bioresonance": [], "follow_up": []}
        }

    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_case
                                  SET results = CAST(:res AS jsonb)
                                  WHERE case_id = :cid
                                  """), {"res": json.dumps(sections), "cid": case_id})
    await session.commit()

    # --- New: recent case history -------------------------------------------------
from typing import Any

@router.get("/history")
async def list_history(limit: int = 25, session: AsyncSession = Depends(get_session)) -> Any:
    """
    Return the most recent cases for the Case History drawer.
    """
    await _ensure_table_runtime(session)
    r = await session.execute(sa_text("""
                                      SELECT case_id::text,
                                          rah_ids,
                                             combination,
                                             analysis_blurb,
                                             recommendations,
                                             created_at,
                                             COALESCE(source,'ai') AS source
                                      FROM rah_schema.checkup_case
                                      ORDER BY created_at DESC
                                          LIMIT :lim
                                      """), {"lim": max(1, min(100, limit))})
    rows = [{
        "case_id": row[0],
        "rah_ids": row[1],
        "combination": row[2],
        "analysis_blurb": row[3],
        "recommendations": row[4],
        "created_at": row[5].isoformat(),
        "source": row[6],
    } for row in r.fetchall()]
    return {"items": rows}

    # Pretty markdown for Stage 4/5
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

    return AnalyzeOut(case_id=case_id, sections=sections, markdown=md)
