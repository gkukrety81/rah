# app/routers/checkup.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text, select
from ..db import get_session
from ..models import RahItem
from ..ollama_client import ollama_generate
import json
import hashlib

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

class TranslateIn(BaseModel):
    case_id: str
    target_lang: str = "de"  # ISO-ish short code; we’ll use prompts

# ---------- Helpers / Prompts ----------
COMBO_TITLE_SYS = (
    "You are given three physiology items. "
    "1) Return a concise 'Combination:' line (<=140 chars) naming overlapping systems. "
    "2) Return a 1–2 sentence neutral 'Analysis:' blurb describing likely shared dysfunction."
)

# We stabilize output by instructing strict JSON and fixed grouping & count.
QUESTION_SYS = (
    "You create a deterministic yes/no questionnaire from three physiology items. "
    "Return EXACTLY 10 items grouped across these buckets: "
    "['Physical','Psychological/Emotional','Functional'] with at least 2 items each. "
    "IDs must be stable, kebab-case, and derived from the text itself (e.g., 'reduced-venous-return'). "
    "Return pure JSON array only, with objects: {\"id\",\"text\",\"group\"}. "
    "NO prose. NO markdown. NO comments. Deterministic phrasing."
)

ANALYZE_SYS = (
    "You are a clinical summarizer. Using selected YES/NO indicators and notes, "
    "return a JSON object with keys and exact shapes:\n"
    "{\n"
    "  \"correlated_systems\": [str, str, str],\n"
    "  \"indications\": [str, str, str],\n"
    "  \"note_synthesis\": str,\n"
    "  \"diagnostic_summary\": str,  // ~200 words\n"
    "  \"recommendations\": {\n"
    "    \"lifestyle\": [str], \"nutritional\": [str], \"emotional\": [str], \"bioresonance\": [str], \"follow_up\": [str]\n"
    "  }\n"
    "}\n"
    "Return JSON ONLY."
)

TRANSLATE_SYS = (
    "Translate the provided markdown into the target language while preserving headings, bullet lists, and formatting. "
    "Do not add or remove content. Return only the translated markdown."
)

# ---------- Tables ----------
CREATE_CASE_SQL = """
                  CREATE TABLE IF NOT EXISTS rah_schema.checkup_case(
                                                                        case_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                      rah_ids        numeric(5,2)[] NOT NULL,
                      combination    text,
                      analysis_blurb text,
                      questions      jsonb,
                      answers        jsonb,
                      notes          text,
                      results        jsonb,
                      created_at     timestamptz NOT NULL DEFAULT now()
                      ); \
                  """

# Q-bank: one row per sorted triple of RAH IDs
CREATE_QBANK_SQL = """
                   CREATE TABLE IF NOT EXISTS rah_schema.checkup_qbank(
                                                                          qkey          text PRIMARY KEY,
                                                                          rah_ids       numeric(5,2)[] NOT NULL,
                       combination   text,
                       analysis_blurb text,
                       questions     jsonb,
                       created_at    timestamptz NOT NULL DEFAULT now()
                       ); \
                   """

async def _ensure_tables(session: AsyncSession):
    await session.execute(sa_text(CREATE_CASE_SQL))
    await session.execute(sa_text(CREATE_QBANK_SQL))
    await session.commit()

def _triple_key(rah_ids: List[float]) -> str:
    triple = ",".join(f"{x:.2f}" for x in sorted(rah_ids))
    return hashlib.md5(triple.encode("utf-8")).hexdigest()

async def _fetch_rah_descriptions(session: AsyncSession, rah_ids: List[float]) -> Dict[float, str]:
    q = await session.execute(
        select(RahItem.rah_id, RahItem.details, RahItem.description).where(RahItem.rah_id.in_(rah_ids))
    )
    by_id: Dict[float, str] = {}
    for rid, details, desc in q.all():
        by_id[float(rid)] = (desc or "").strip() or (details or "").strip()
    return by_id

# ---------- Endpoints ----------

@router.post("/start", response_model=StartOut)
async def start(payload: StartIn, session: AsyncSession = Depends(get_session)):
    await _ensure_tables(session)
    if len(payload.rah_ids) != 3:
        raise HTTPException(400, "Exactly 3 RAH IDs are required.")

    # Use descriptions as context; ensures grounded & repeatable signals
    by_id = await _fetch_rah_descriptions(session, payload.rah_ids)
    if len(by_id) < 3:
        missing = [x for x in payload.rah_ids if x not in by_id]
        raise HTTPException(400, f"Unknown RAH IDs: {missing}")

    context = "\n\n".join([f"RAH {rid:.2f}:\n{by_id[rid]}" for rid in payload.rah_ids])

    # Check Q-bank cache first
    qkey = _triple_key(payload.rah_ids)
    row = await session.execute(sa_text(
        "SELECT combination, analysis_blurb, questions FROM rah_schema.checkup_qbank WHERE qkey=:k"
    ), {"k": qkey})
    cached = row.first()

    if cached:
        combination, blurb, questions_json = cached
        questions = questions_json or []
    else:
        # Generate combo + analysis
        combo_raw = await ollama_generate(
            f"Descriptions from three RAH items:\n\n{context}\n\n"
            "Return two lines exactly labeled 'Combination:' and 'Analysis:'",
            system=COMBO_TITLE_SYS
        )
        combination, blurb = "", ""
        for line in combo_raw.splitlines():
            if line.lower().startswith("combination:"):
                combination = line.split(":", 1)[1].strip()
            elif line.lower().startswith("analysis:"):
                blurb = line.split(":", 1)[1].strip()

        # Generate deterministic questionnaire (10 items, stable groups)
        qjson_text = await ollama_generate(
            f"Descriptions from three RAH items:\n\n{context}\n\nReturn JSON array now.",
            system=QUESTION_SYS
        )
        try:
            parsed = json.loads(qjson_text)
            questions = []
            for q in parsed:
                if isinstance(q, dict) and {"id", "text", "group"} <= set(q):
                    # normalize
                    questions.append({
                        "id": str(q["id"]),
                        "text": str(q["text"]),
                        "group": str(q["group"])
                    })
        except Exception:
            questions = []

        # Store to Q-bank
        await session.execute(sa_text("""
                                      INSERT INTO rah_schema.checkup_qbank (qkey, rah_ids, combination, analysis_blurb, questions)
                                      VALUES (:k, :ids, :c, :b, CAST(:q AS jsonb))
                                          ON CONFLICT (qkey) DO NOTHING
                                      """), {"k": qkey, "ids": sorted(payload.rah_ids), "c": combination, "b": blurb, "q": json.dumps(questions)})
        await session.commit()

    # Create a case using cached/generated
    row = await session.execute(sa_text("""
                                        INSERT INTO rah_schema.checkup_case (rah_ids, combination, analysis_blurb, questions)
                                        VALUES (:ids, :c, :b, CAST(:q AS jsonb))
                                            RETURNING case_id::text
                                        """), {"ids": payload.rah_ids, "c": combination, "b": blurb, "q": json.dumps(questions)})
    case_id = row.scalar_one()
    await session.commit()


    return StartOut(
        case_id=case_id,
        rah_ids=payload.rah_ids,
        combination_title=combination or "Combination",
        analysis_blurb=blurb or "",
        questions=[Question(**q) for q in (questions or [])]
    )

@router.post("/answers")
async def save_answers(payload: AnswersIn, session: AsyncSession = Depends(get_session)):
    await _ensure_tables(session)
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_case
                                  SET answers = CAST(:a AS jsonb), notes=:n
                                  WHERE case_id=:cid
                                  """), {"a": json.dumps(payload.selected or []), "n": payload.notes or "", "cid": payload.case_id})
    await session.commit()
    return {"ok": True}

@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    await _ensure_tables(session)
    res = await session.execute(sa_text("""
                                        SELECT case_id::text, rah_ids, combination, analysis_blurb, questions, answers, notes
                                        FROM rah_schema.checkup_case WHERE case_id=:cid
                                        """), {"cid": payload.case_id})
    row = res.first()
    if not row:
        raise HTTPException(404, "Unknown case_id")
    case_id, rah_ids, combination, blurb, questions_json, answers_json, notes = row

    # Build selected questions summary
    questions = questions_json or []
    selected_ids = set(answers_json or [])
    picked = [q for q in questions if q.get("id") in selected_ids]

    # Ground context again
    by_id = await _fetch_rah_descriptions(session, rah_ids)
    context = "\n\n".join([f"RAH {float(r):.2f}:\n{by_id.get(float(r),'')}" for r in rah_ids])

    user_prompt = (
            f"Combination: {combination}\n"
            f"Short analysis: {blurb}\n\n"
            f"Descriptions:\n{context}\n\n"
            f"Selected indicators (YES):\n" +
            "\n".join([f"- [{q.get('group')}] {q.get('text')}" for q in picked]) +
            f"\n\nPractitioner notes:\n{notes or '(none)'}\n\nReturn JSON only."
    )

    raw = await ollama_generate(user_prompt, system=ANALYZE_SYS)
    try:
        sections = json.loads(raw)
    except Exception:
        sections = {
            "correlated_systems": [],
            "indications": [],
            "note_synthesis": "",
            "diagnostic_summary": raw.strip(),
            "recommendations": {
                "lifestyle": [], "nutritional": [], "emotional": [], "bioresonance": [], "follow_up": []
            }
        }

    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_case SET results=CAST(:r AS jsonb) WHERE case_id=:cid
                                  """), {"r": json.dumps(sections), "cid": case_id})
    await session.commit()

    def bullets(items):
        return "\n".join([f"- {x}" for x in (items or [])])
    rec = sections.get("recommendations", {}) or {}
    md = f"""# RAI Analysis

## Correlated Systems Analysis
{bullets(sections.get("correlated_systems", []))}

## Indication Interpretation
{bullets(sections.get("indications", []))}

## Note Synthesis
{sections.get("note_synthesis","")}

## 200-Word Diagnostic Summary
{sections.get("diagnostic_summary","")}

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

@router.post("/translate")
async def translate(payload: TranslateIn, session: AsyncSession = Depends(get_session)):
    # Load last results
    r = await session.execute(sa_text("SELECT results FROM rah_schema.checkup_case WHERE case_id=:c"), {"c": payload.case_id})
    row = r.first()
    if not row or not row[0]:
        raise HTTPException(404, "No results for case")
    results = row[0]
    # Rebuild the markdown the same way analyze() does
    def bullets(items): return "\n".join([f"- {x}" for x in (items or [])])
    rec = results.get("recommendations", {}) or {}
    md = f"""# RAI Analysis

## Correlated Systems Analysis
{bullets(results.get("correlated_systems", []))}

## Indication Interpretation
{bullets(results.get("indications", []))}

## Note Synthesis
{results.get("note_synthesis","")}

## 200-Word Diagnostic Summary
{results.get("diagnostic_summary","")}

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

    lang_label = {"de": "German", "fr": "French", "it": "Italian", "es": "Spanish"}.get(payload.target_lang.lower(), payload.target_lang)
    translated = await ollama_generate(
        f"Target language: {lang_label}\n\nMarkdown to translate:\n\n{md}",
        system=TRANSLATE_SYS
    )
    return {"markdown": translated}
