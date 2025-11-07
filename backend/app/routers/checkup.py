# backend/app/routers/checkup.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
import re
import json

from app.db import get_session
from app.ai import run_analysis_sections, harmonise_bioresonance

# PDF / ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)

router = APIRouter(prefix="/checkup", tags=["checkup"])


# ----------------------------- Helpers -----------------------------


def _clean_blurb(text: str) -> str:
    if not text:
        return ""
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


async def _fetch_labels(session: AsyncSession, ids_sorted: List[float]) -> Dict[float, str]:
    """
    Fetch human labels for the given program codes without assuming a fixed column name.
    We read the whole row as JSON and pick the first sensible key.
    """
    res = await session.execute(
        sa_text(
            """
            SELECT program_code::numeric(5,2) AS code, to_jsonb(p) AS obj
            FROM rah_schema.physiology_program p
            WHERE program_code = ANY(:ids)
            """
        ),
        {"ids": ids_sorted},
    )
    rows = res.fetchall()
    labels: Dict[float, str] = {}
    candidates = ("label", "title", "name", "program", "description")
    for code, obj in rows:
        label = ""
        if isinstance(obj, dict):
            for k in candidates:
                if k in obj and obj[k]:
                    label = str(obj[k])
                    break
        labels[float(code)] = label or f"{float(code):.2f}"
    return labels


def _build_case_pdf(
        *,
        case_id: str,
        rah_ids: List[float],
        rah_labels: Optional[List[str]],
        combination_title: str,
        sections: Dict[str, Any],
) -> bytes:
    """
    Build a nicely formatted PDF for a given case_id + analysis sections.

    - rah_ids:      [42.0, 46.0, 58.0]
    - rah_labels:   ["Respiratory system, physiology complete", ...]
    - combination_title: e.g. "Nasal-Eustachian Tube-Eardrum"
    - sections:     the JSON structure stored in checkup_result.sections
    """

    # Fall back to codes if labels list is empty/misaligned
    if rah_labels and len(rah_labels) == len(rah_ids):
        names = rah_labels
    else:
        names = [f"RAH {float(x):.2f}" for x in rah_ids]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleH1",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        spaceBefore=8,
        spaceAfter=4,
    )
    normal = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=10,
        leading=13,
        spaceAfter=2,
    )
    subtle = ParagraphStyle(
        "Subtle",
        parent=normal,
        textColor="#666666",
        fontSize=8,
        leading=10,
        spaceAfter=2,
    )

    story: List[Any] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    story.append(Paragraph("RAI Analysis Report", title_style))
    story.append(Paragraph(f"Case ID: {case_id}", subtle))
    story.append(Spacer(1, 6 * mm))

    # ------------------------------------------------------------------
    # Combination meta
    # ------------------------------------------------------------------
    if rah_ids:
        codes_line = ", ".join(f"{x:.2f}" for x in rah_ids)
        labels_line = ", ".join(names)
        story.append(Paragraph("RAH Combination", h2))
        story.append(Paragraph(f"Codes: {codes_line}", normal))
        story.append(Paragraph(f"Physiologies: {labels_line}", normal))
        if combination_title:
            story.append(Paragraph(f"Profile: {combination_title}", normal))
        story.append(Spacer(1, 5 * mm))

    # ------------------------------------------------------------------
    # Correlated Systems
    # ------------------------------------------------------------------
    corr = sections.get("correlated_systems") or []
    if corr:
        story.append(Paragraph("Correlated Systems Analysis", h2))
        bullets = [
            ListItem(Paragraph(str(c), normal), bulletColor="black") for c in corr
        ]
        story.append(ListFlowable(bullets, bulletType="bullet"))
        story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # Indication Interpretation
    # ------------------------------------------------------------------
    inds = sections.get("indications") or []
    if inds:
        story.append(Paragraph("Indication Interpretation", h2))
        bullets = [
            ListItem(
                Paragraph(str(i).replace("**", ""), normal), bulletColor="black"
            )
            for i in inds
        ]
        story.append(ListFlowable(bullets, bulletType="bullet"))
        story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # Note Synthesis
    # ------------------------------------------------------------------
    note = (sections.get("note_synthesis") or "").strip()
    if note:
        story.append(Paragraph("Note Synthesis", h2))
        story.append(Paragraph(note, normal))
        story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 200-Word Diagnostic Summary
    # ------------------------------------------------------------------
    summary = (sections.get("diagnostic_summary") or "").strip()
    if summary:
        story.append(Paragraph("200-Word Diagnostic Summary", h2))
        story.append(Paragraph(summary, normal))
        story.append(Spacer(1, 6 * mm))

    # ------------------------------------------------------------------
    # Tailored Recommendations
    # ------------------------------------------------------------------
    rec = sections.get("recommendations") or {}
    if any(
            rec.get(k)
            for k in ["lifestyle", "nutritional", "emotional", "bioresonance", "follow_up"]
    ):
        story.append(Paragraph("Tailored Recommendations", h2))
        story.append(Spacer(1, 2 * mm))

        def add_bucket(title: str, key: str) -> None:
            items = rec.get(key) or []
            if not items:
                return
            story.append(Paragraph(f"<b>{title}</b>", normal))
            bullets = [
                ListItem(Paragraph(str(i), normal), bulletColor="black")
                for i in items
            ]
            story.append(ListFlowable(bullets, bulletType="bullet"))
            story.append(Spacer(1, 2 * mm))

        add_bucket("Lifestyle", "lifestyle")
        add_bucket("Nutritional", "nutritional")
        add_bucket("Emotional", "emotional")
        add_bucket("Rayonex Bioresonance", "bioresonance")
        add_bucket("Follow-Up", "follow_up")

    # Build PDF
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ----------------------------- Models -----------------------------


class StartIn(BaseModel):
    rah_ids: List[float] = Field(min_items=3, max_items=3)


class StartOut(BaseModel):
    ok: bool = True
    case_id: str
    rah_ids: List[float]
    rah_labels: List[str] = []
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
async def start_checkup(
        payload: StartIn, session: AsyncSession = Depends(get_session)
):
    ids_sorted = sorted(float(x) for x in payload.rah_ids)
    key = _triad_key(ids_sorted)

    # Validate the 3 codes and fetch human labels
    labels_map = await _fetch_labels(session, ids_sorted)
    if len(labels_map) != 3:
        raise HTTPException(
            status_code=400,
            detail="Invalid RAH IDs. Only the 21 official physiologies (30–76) are accepted.",
        )

    # Preserve the original input order for display
    rah_labels_in_input_order = [labels_map.get(float(x), "") for x in payload.rah_ids]

    # Look up the triad combination
    row = await session.execute(
        sa_text(
            """
            SELECT combination_id::text,
                rah_ids,
                   combination_title,
                   analysis,
                   potential_indications,
                   recommendations
            FROM rah_schema.rah_combination_profiles
            WHERE combo_key = :k
                LIMIT 1
            """
        ),
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
                    qid = f"{group[:3].upper()}-{i + 1}"
                    questions.append({"id": qid, "text": text_item, "group": group})
        except Exception:
            questions = []

        # ORIGINAL recommendations text from the triad profile
        original_reco = str(comb[5] or "")

        # 🔁 Harmonise Rayonex Bioresonance once, so Stage 3 and 4 share it
        patched_reco, _bio_lines = harmonise_bioresonance(ids_sorted, original_reco)

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
                "reco": patched_reco,
            },
        )
        case_id = ins.scalar_one()
        await session.commit()

        return StartOut(
            case_id=case_id,
            rah_ids=ids_sorted,
            rah_labels=rah_labels_in_input_order,
            combination_title=str(comb[2] or ""),
            analysis_blurb=_clean_blurb(str(comb[3] or "")),
            questions=questions,
            recommendations=patched_reco,  # 👈 this is what Stage 3 shows
            source="db",
        )


# AI fallback path – no curated triad yet, but we still create a case
    ins = await session.execute(
        sa_text(
            """
            INSERT INTO rah_schema.checkup_case
            (rah_ids, combination, analysis_blurb, questions, recommendations, source)
            VALUES (:rah, '', '', '[]'::jsonb, '', 'ai')
                RETURNING case_id::text
            """
        ),
        {"rah": ids_sorted},
    )
    case_id = ins.scalar_one()
    await session.commit()

    return StartOut(
        case_id=case_id,
        rah_ids=ids_sorted,
        rah_labels=rah_labels_in_input_order,
        combination_title="",
        analysis_blurb="",
        questions=[],
        recommendations="",
        source="ai",
    )


@router.post("/answers")
async def save_answers(
        payload: SaveAnswersIn, session: AsyncSession = Depends(get_session)
):
    """Store practitioner selections/notes."""
    cid = (payload.case_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="case_id required")

    selected = payload.selected or []
    notes = (payload.notes or "").strip()

    exists = await session.execute(
        sa_text(
            """
            SELECT 1
            FROM rah_schema.checkup_case
            WHERE case_id = CAST(:cid AS uuid)
                LIMIT 1
            """
        ),
        {"cid": cid},
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    await session.execute(
        sa_text(
            """
            INSERT INTO rah_schema.checkup_answers (case_id, selected_ids, notes)
            VALUES (CAST(:cid AS uuid), CAST(:sel AS text[]), :notes)
                ON CONFLICT (case_id)
        DO UPDATE SET
                selected_ids = EXCLUDED.selected_ids,
                               notes        = EXCLUDED.notes,
                               updated_at   = now()
            """
        ),
        {"cid": cid, "sel": selected, "notes": notes},
    )
    await session.commit()
    return {"ok": True}


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn, session: AsyncSession = Depends(get_session)):
    # Fetch case, including stored questions JSON
    case_q = await session.execute(
        sa_text(
            """
            SELECT case_id::text,
                rah_ids,
                   COALESCE(combination, '')      AS combination,
                   COALESCE(analysis_blurb, '')   AS analysis_blurb,
                   COALESCE(recommendations, '')  AS recommendations,
                   COALESCE(questions, '[]'::jsonb) AS questions
            FROM rah_schema.checkup_case
            WHERE case_id = CAST(:cid AS uuid)
                LIMIT 1
            """
        ),
        {"cid": payload.case_id},
    )
    case = case_q.first()
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    # Answers (checkbox selections + notes)
    ans_q = await session.execute(
        sa_text(
            """
            SELECT COALESCE(selected_ids, ARRAY[]::text[]) AS selected_ids,
                   COALESCE(notes, '')                    AS notes
            FROM rah_schema.checkup_answers
            WHERE case_id = CAST(:cid AS uuid)
                LIMIT 1
            """
        ),
        {"cid": payload.case_id},
    )
    ans = ans_q.first()
    selected_ids = list(ans[0]) if ans else []
    notes = str(ans[1] or "") if ans else ""

    # Questions JSON – already stored as list[dict] in checkup_case.questions
    raw_q = case[5]
    if isinstance(raw_q, list):
        questions: List[Dict[str, Any]] = raw_q
    else:
        # Defensive: try to decode if it came back as a JSON string
        try:
            decoded = json.loads(raw_q)
            questions = decoded if isinstance(decoded, list) else []
        except Exception:
            questions = []

    # Build analysis sections
    try:
        sections = await run_analysis_sections(
            rah_ids=[float(x) for x in case[1]],
            combination=str(case[2] or ""),
            analysis_blurb=_clean_blurb(str(case[3] or "")),
            selected_ids=selected_ids,
            notes=notes,
            recommendations=str(case[4] or ""),
            questions=questions,
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

    def bullets(items: List[str]) -> str:
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

    # Persist result for history
    await session.execute(
        sa_text(
            """
            INSERT INTO rah_schema.checkup_result (case_id, sections, markdown)
            VALUES (CAST(:cid AS uuid), CAST(:sec AS jsonb), :md)
                ON CONFLICT (case_id)
        DO UPDATE SET
                sections = EXCLUDED.sections,
                               markdown = EXCLUDED.markdown
            """
        ),
        {"cid": payload.case_id, "sec": json.dumps(sections), "md": md},
    )
    await session.commit()

    return AnalyzeOut(case_id=payload.case_id, sections=sections, markdown=md)


# ----------------------------- PDF Route -----------------------------


@router.get("/report/{case_id}/pdf")
async def download_report(case_id: str, session: AsyncSession = Depends(get_session)):
    """
    Return a server-side generated PDF for an analyzed case.
    Requires that /checkup/analyze has already been run for this case_id
    (so that rah_schema.checkup_result has a row).
    """
    cid = (case_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="case_id required")

    # 1) Fetch the base case info
    case_q = await session.execute(
        sa_text(
            """
            SELECT rah_ids, COALESCE(combination, '') AS combination
            FROM rah_schema.checkup_case
            WHERE case_id = CAST(:cid AS uuid)
                LIMIT 1
            """
        ),
        {"cid": cid},
    )
    case = case_q.first()
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    rah_ids = [float(x) for x in (case[0] or [])]
    combination_title = str(case[1] or "")

    # Fetch labels for the PDF header
    labels_map = await _fetch_labels(session, sorted(rah_ids))
    rah_labels = [labels_map.get(x, f"RAH {x:.2f}") for x in rah_ids]

    # 2) Fetch analyzed sections (must exist)
    res_q = await session.execute(
        sa_text(
            """
            SELECT sections
            FROM rah_schema.checkup_result
            WHERE case_id = CAST(:cid AS uuid)
                LIMIT 1
            """
        ),
        {"cid": cid},
    )
    res_row = res_q.first()
    if not res_row:
        raise HTTPException(
            status_code=400,
            detail="Analysis not yet generated for this case. Run RAI Analyze first.",
        )

    sections = res_row[0] or {}

    pdf_bytes = _build_case_pdf(
        case_id=cid,
        rah_ids=rah_ids,
        rah_labels=rah_labels,
        combination_title=combination_title,
        sections=sections,
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rai-report-{cid}.pdf"'
        },
    )
