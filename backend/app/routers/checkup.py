from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from uuid import UUID
from sqlalchemy import text as sa_text, select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_session
from ..auth_utils import get_current_user
from ..ollama_client import ollama_generate

router = APIRouter(prefix="/checkup", tags=["checkup"])

# ---------- Models (Pydantic) ----------
class CreateSessionIn(BaseModel):
    rah_id_1: float
    rah_id_2: float
    rah_id_3: float

class IndicationItem(BaseModel):
    category: Literal["Physical", "Emotional", "Functional"]
    label: str
    selected: bool = False

class Stage2Payload(BaseModel):
    combination: str
    analysis: str
    potential_indications: List[IndicationItem]
    recommendations: Dict[str, List[str]]  # lifestyle, nutritional, emotional, bior, follow_up

class UpdateSessionIn(BaseModel):
    practitioner_notes: Optional[str] = None
    status: Optional[str] = None

class AnalyzeOut(BaseModel):
    correlated_systems: List[str]
    interpretation: List[Dict[str, str]]
    note_synthesis: str
    diagnostic_summary: str
    recommendations: Dict[str, List[str]]

# ---------- Helpers ----------
async def _require_owner(sess: AsyncSession, session_id: UUID, user_id: UUID) -> None:
    row = await sess.execute(sa_text("""
                                     SELECT created_by FROM rah_schema.checkup_session WHERE id = :id
                                     """), {"id": str(session_id)})
    r = row.first()
    if not r: raise HTTPException(404, "Session not found")
    if str(r[0]) != str(user_id): raise HTTPException(403, "Forbidden")

# ---------- Stage 1: Create ----------
@router.post("/sessions")
async def create_session(body: CreateSessionIn, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    res = await session.execute(sa_text("""
                                        INSERT INTO rah_schema.checkup_session (created_by, rah_id_1, rah_id_2, rah_id_3, status)
                                        VALUES (:u, :a, :b, :c, 'draft') RETURNING id
                                        """), {"u": str(user.user_id), "a": body.rah_id_1, "b": body.rah_id_2, "c": body.rah_id_3})
    id_ = res.scalar_one()
    await session.commit()
    return {"id": str(id_)}

# ---------- Get / Update ----------
@router.get("/sessions/{session_id}")
async def get_session_full(session_id: UUID, session: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    await _require_owner(session, session_id, user.user_id)
    q = await session.execute(sa_text("""
                                      SELECT id, created_by, rah_id_1, rah_id_2, rah_id_3, status, practitioner_notes, stage2_payload::text
                                      FROM rah_schema.checkup_session WHERE id = :id
                                      """), {"id": str(session_id)})
    s = q.first()
    if not s: raise HTTPException(404, "Not found")

    ind = await session.execute(sa_text("""
                                        SELECT category, label, selected FROM rah_schema.checkup_indication WHERE session_id = :id ORDER BY category, label
                                        """), {"id": str(session_id)})

    res = await session.execute(sa_text("""
                                        SELECT correlated_systems::text, interpretation::text, note_synthesis, diagnostic_summary, recommendations::text
                                        FROM rah_schema.checkup_result WHERE session_id = :id
                                        """), {"id": str(session_id)})

    r = res.first()
    return {
        "session": {
            "id": str(s[0]), "rah_id_1": float(s[2]), "rah_id_2": float(s[3]), "rah_id_3": float(s[4]),
            "status": s[5], "practitioner_notes": s[6],
            "stage2_payload": s[7] and s[7]
        },
        "indications": [dict(row._mapping) for row in ind.fetchall()],
        "result": r and {
            "correlated_systems": r[0] and r[0],
            "interpretation": r[1] and r[1],
            "note_synthesis": r[2],
            "diagnostic_summary": r[3],
            "recommendations": r[4] and r[4],
        }
    }

@router.patch("/sessions/{session_id}")
async def update_session(session_id: UUID, body: UpdateSessionIn, session: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    await _require_owner(session, session_id, user.user_id)
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_session
                                  SET practitioner_notes = COALESCE(:notes, practitioner_notes),
                                      status = COALESCE(:status, status),
                                      updated_at = now()
                                  WHERE id = :id
                                  """), {"id": str(session_id), "notes": body.practitioner_notes, "status": body.status})
    await session.commit()
    return {"ok": True}

# ---------- Stage 2 generation ----------
@router.post("/sessions/{session_id}/stage2")
async def build_stage2(session_id: UUID, session: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    await _require_owner(session, session_id, user.user_id)
    r = await session.execute(sa_text("""
                                      SELECT rah_id_1, rah_id_2, rah_id_3
                                      FROM rah_schema.checkup_session WHERE id = :id
                                      """), {"id": str(session_id)})
    row = r.first();
    if not row: raise HTTPException(404, "Not found")
    a, b, c = float(row[0]), float(row[1]), float(row[2])

    # Fetch source texts for the three RAH IDs
    src = await session.execute(sa_text("""
                                        SELECT rah_id, COALESCE(NULLIF(description,''), details) AS text
                                        FROM rah_schema.rah_item
                                        WHERE rah_id IN (:a,:b,:c) ORDER BY rah_id
                                        """), {"a": a, "b": b, "c": c})
    snippets = [f"{float(r[0]):.2f} — {r[1]}" for r in src.fetchall()]

    prompt = f"""
You are a clinical assistant. Given three RAH items and their narratives, produce Stage-2 content in JSON only.

RAH sources:
{chr(10).join('- ' + s for s in snippets)}

Respond strictly as JSON with keys:
combination: string,
analysis: string,
potential_indications: array of objects {{category: "Physical"|"Emotional"|"Functional", label: string}},
recommendations: object {{
  lifestyle: string[], nutritional: string[], emotional: string[], bior: string[], follow_up: string[]
}}
"""
    raw = await ollama_generate(prompt, system="Return valid, compact JSON. No prose outside JSON.")
    # raw is a string; store as text JSON
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_session
                                  SET stage2_payload = :j::jsonb, status='questionnaire', updated_at=now()
                                  WHERE id = :id
                                  """), {"id": str(session_id), "j": raw})
    # seed indications table
    await session.execute(sa_text("DELETE FROM rah_schema.checkup_indication WHERE session_id=:id"), {"id": str(session_id)})
    await session.execute(sa_text("""
                                  INSERT INTO rah_schema.checkup_indication(session_id, category, label, selected)
                                  SELECT :id, (i->>'category'), (i->>'label'), false
                                  FROM jsonb_path_query(:j::jsonb, '$.potential_indications[*]') AS i
                                  """), {"id": str(session_id), "j": raw})
    await session.commit()
    return {"ok": True}

# ---------- Save indications ----------
@router.post("/sessions/{session_id}/indications")
async def save_indications(session_id: UUID, items: List[IndicationItem], session: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    await _require_owner(session, session_id, user.user_id)
    # simple upsert
    for it in items:
        await session.execute(sa_text("""
                                      INSERT INTO rah_schema.checkup_indication(session_id, category, label, selected)
                                      VALUES (:id, :cat, :lbl, :sel)
                                          ON CONFLICT (session_id, category, label) DO UPDATE SET selected=EXCLUDED.selected
                                      """.replace("ON CONFLICT (session_id, category, label)",
                                                  "ON CONFLICT DO NOTHING")),  # if you want a true composite unique, add it in DDL
                              {"id": str(session_id), "cat": it.category, "lbl": it.label, "sel": it.selected})
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_session SET status='notes', updated_at=now() WHERE id=:id
                                  """), {"id": str(session_id)})
    await session.commit()
    return {"ok": True}

# ---------- Stage 4/5 Analysis ----------
@router.post("/sessions/{session_id}/analyze")
async def analyze(session_id: UUID, session: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    await _require_owner(session, session_id, user.user_id)
    q = await session.execute(sa_text("""
                                      SELECT rah_id_1, rah_id_2, rah_id_3, practitioner_notes, stage2_payload::text
                                      FROM rah_schema.checkup_session WHERE id=:id
                                      """), {"id": str(session_id)})
    s = q.first()
    if not s: raise HTTPException(404, "Not found")
    a,b,c, notes, stage2 = float(s[0]), float(s[1]), float(s[2]), (s[3] or ""), (s[4] or "{}")

    ind = await session.execute(sa_text("""
                                        SELECT category, label, selected FROM rah_schema.checkup_indication
                                        WHERE session_id=:id ORDER BY category, label
                                        """), {"id": str(session_id)})
    chosen = [dict(r._mapping) for r in ind.fetchall()]

    prompt = f"""
You are a clinical reasoning engine. Using the selected indications and practitioner notes,
produce a structured JSON report with keys:
correlated_systems: string[]  (3–5 bullet items),
interpretation: array of objects {{title: string, body: string}},
note_synthesis: string,
diagnostic_summary: string,   -- 200–1000 words, coherent and professional, no diagnoses
recommendations: object {{ lifestyle: string[], nutritional: string[], emotional: string[], bior: string[], follow_up: string[] }}

Inputs:
RAH IDs: {a:.2f}, {b:.2f}, {c:.2f}
Stage2 summary (JSON string): {stage2}
Selected indications: {chosen}
Practitioner notes: {notes}

Return JSON only. Keep it concise and grounded in the inputs. Avoid medical claims; use advisory language.
"""
    raw = await ollama_generate(prompt, system="Return valid JSON. No extra text.")
    await session.execute(sa_text("""
                                  INSERT INTO rah_schema.checkup_result(
                                      session_id, correlated_systems, interpretation, note_synthesis, diagnostic_summary, recommendations, raw_model_output
                                  )
                                  SELECT :id,
                                         (j->'correlated_systems')::jsonb,
                                      (j->'interpretation')::jsonb,
                                      (j->>'note_synthesis'),
                                         (j->>'diagnostic_summary'),
                                         (j->'recommendations')::jsonb,
                                      j::jsonb
                                  FROM (SELECT :raw::jsonb AS j) x
                                      ON CONFLICT (session_id) DO UPDATE
                                                                      SET correlated_systems = EXCLUDED.correlated_systems,
                                                                      interpretation     = EXCLUDED.interpretation,
                                                                      note_synthesis     = EXCLUDED.note_synthesis,
                                                                      diagnostic_summary = EXCLUDED.diagnostic_summary,
                                                                      recommendations    = EXCLUDED.recommendations,
                                                                      raw_model_output   = EXCLUDED.raw_model_output
                                  """), {"id": str(session_id), "raw": raw})
    await session.execute(sa_text("""
                                  UPDATE rah_schema.checkup_session SET status='analyzed', updated_at=now() WHERE id=:id
                                  """), {"id": str(session_id)})
    await session.commit()
    return {"ok": True}
