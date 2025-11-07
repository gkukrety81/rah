# backend/app/ai.py
from __future__ import annotations

import os
import httpx
from typing import List, Dict, Any

# ---- Ollama helpers -------------------------------------------------

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
GEN_MODEL = os.getenv("GEN_MODEL", "llama3.1:8b")


async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json().get("embedding", [])


async def generate(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": GEN_MODEL, "prompt": prompt, "stream": False},
        )
        r.raise_for_status()
        j = r.json()
        return j.get("response", "").strip()


# --------------------------------------------------------------------
#  Friendly labels for the 21 official physiologies
# --------------------------------------------------------------------

PHYSIO_LABELS: Dict[float, str] = {
    30.00: "Cells & tissue",
    32.00: "Blood",
    34.00: "Immune system",
    36.00: "Lymphatic system",
    38.00: "Circulatory system",
    40.00: "Heart",
    42.00: "Respiratory system",
    44.00: "Kidney / urinary",
    46.00: "Digestive system",
    48.00: "Liver–gall–pancreas",
    50.00: "Metabolism",
    52.00: "Musculoskeletal",
    54.00: "Nervous system",
    56.00: "Vision",
    58.00: "Acoustic / equilibrium",
    62.00: "Skin / hair",
    64.00: "Hormonal system",
    66.00: "Female sexual organs",
    68.00: "Male sexual organs",
    72.00: "Psyche",
    75.00: "Stress",
    76.00: "Teeth (overall)",
}


def _bullets(items: List[str]) -> List[str]:
    return [str(s).strip() for s in (items or []) if str(s).strip()]


def _selected_texts(
        questions: List[Dict[str, Any]], selected_ids: List[str]
) -> Dict[str, List[str]]:
    by_group: Dict[str, List[str]] = {
        "Physical": [],
        "Psychological/Emotional": [],
        "Functional": [],
    }
    sel = set(selected_ids or [])
    for q in questions or []:
        try:
            if q.get("id") in sel:
                grp = q.get("group") or "Physical"
                by_group.setdefault(grp, []).append(str(q.get("text", "")).strip())
        except Exception:
            continue

    # de-dupe while preserving order
    for k, arr in by_group.items():
        seen = set()
        dedup = []
        for s in arr:
            if s and s not in seen:
                seen.add(s)
                dedup.append(s)
        by_group[k] = dedup
    return by_group


def _recommendations_from_text(blob: str) -> Dict[str, List[str]]:
    """
    Split the DB 'recommendations' text into buckets if it already contains
    headings/bullets. Otherwise provide safe defaults.
    """
    if not (blob or "").strip():
        return {
            "lifestyle": [
                "Engage in light-to-moderate activity as tolerated.",
                "Prioritize consistent, restorative sleep (7–9 hours).",
            ],
            "nutritional": [
                "Favor a whole-food, anti-inflammatory pattern with adequate protein.",
                "Maintain good hydration across the day.",
            ],
            "emotional": [
                "Practice brief daily stress reduction (breathing, meditation, journaling).",
            ],
            "bioresonance": [],
            "follow_up": [
                "Reassess progress and tailor steps with practitioner input.",
            ],
        }

    buckets = {
        "lifestyle": [],
        "nutritional": [],
        "emotional": [],
        "bioresonance": [],
        "follow_up": [],
    }

    text = blob.replace("\r\n", "\n")
    headings = [
        ("diet", "nutritional"),
        ("nutrition", "nutritional"),
        ("lifestyle", "lifestyle"),
        ("stress", "emotional"),
        ("emotional", "emotional"),
        ("rayonex", "bioresonance"),
        ("follow-up", "follow_up"),
        ("follow up", "follow_up"),
    ]

    current = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue

        low = line.lower()
        moved = False
        for needle, key in headings:
            # treat a line with 'X:' near start as a heading
            if needle in low and ":" in low[:40]:
                current = key
                moved = True
                break
        if moved:
            continue

        if line.startswith(("*", "-", "•")):
            if current is None:
                current = "lifestyle"
            buckets[current].append(line.lstrip("*•- ").strip())

    for k in list(buckets.keys()):
        buckets[k] = _bullets(buckets[k])

    if not any(buckets.values()):
        return _recommendations_from_text("")
    return buckets


# --------------------------------------------------------------------
#  NEW: harmonise_bioresonance
#  - removes raw program-number bullets
#  - keeps a single "After individual balancing…" line
#  - adds generic Rayonex suggestions based on keywords
# --------------------------------------------------------------------


def harmonise_bioresonance(
        rah_ids: List[float], recommendations_text: str
) -> tuple[str, List[str]]:
    """
    Take the free-text recommendations blob and normalise the
    Rayonex Bioresonance section.

    Returns:
        (patched_recommendations_text, bio_bullets)
    """

    text = (recommendations_text or "").replace("\r\n", "\n")
    lower = text.lower()
    header = "Rayonex Bioresonance:"

    # Strip any existing Rayonex block – we’ll replace it.
    idx = lower.find("rayonex bioresonance")
    if idx != -1:
        base = text[:idx].rstrip()
    else:
        base = text.rstrip()

    # Build the canonical "after individual balancing" line
    names = [
        PHYSIO_LABELS.get(float(x), f"RAH {float(x):.2f}")
        for x in sorted(float(v) for v in (rah_ids or []))
    ]
    if len(names) == 3:
        combo_phrase = (
            f"After individual balancing, use combination programs that address "
            f"{names[0]}, {names[1]} and {names[2]} together to harmonise their interaction."
        )
    elif names:
        combo_phrase = (
                "After individual balancing, use combination programs that address "
                + ", ".join(names)
                + " together to harmonise their interaction."
        )
    else:
        combo_phrase = (
            "After individual balancing, use combination programs that support the "
            "key physiologies involved to harmonise their interaction."
        )

    bullets: List[str] = [combo_phrase]

    # Use the FULL original text (before stripping) for keyword detection
    keyword_text = lower

    def add_if(words: List[str], sentence: str) -> None:
        if any(w in keyword_text for w in words) and sentence not in bullets:
            bullets.append(sentence)

    add_if(
        ["detox", "toxin"],
        "Use programs that support detoxification and elimination pathways alongside lifestyle changes.",
    )
    add_if(
        ["energy", "fatigue", "tired"],
        "Use programs that support overall energy, vitality, and recovery.",
    )
    add_if(
        ["digest", "bloat", "indigestion", "gut", "nutrition", "diet"],
        "Use programs that support digestion and nutrient absorption alongside nutritional changes.",
    )
    add_if(
        ["immune", "infection", "inflamm"],
        "Use immune-modulating frequencies to support balanced inflammatory and defence responses.",
    )
    add_if(
        ["stress", "anxiety", "emotional", "mood"],
        "Use stress-regulation and emotional balancing programs to complement relaxation techniques.",
    )
    add_if(
        ["sleep", "insomnia"],
        "Use programs that promote restorative sleep and circadian balance.",
    )

    # Compose new Rayonex block (no RAH numbers)
    bio_block_lines = [header] + ["- " + s for s in bullets]
    new_section = "\n".join(bio_block_lines)

    if base:
        patched = base + "\n\n" + new_section
    else:
        patched = new_section

    return patched, bullets


# --------------------------------------------------------------------
#  NEW: rewrite explanatory indications -> symptom-style questions
# --------------------------------------------------------------------


def _looks_like_question(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    starts = ("do ", "does ", "have you", "are you", "is there", "did you", "have they")
    return any(t.startswith(s) for s in starts)


async def rewrite_indications_to_questions(
        potential_indications: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Take the JSON structure from rah_combination_profiles.potential_indications
    and rewrite each item as a short, client-friendly yes/no symptom question.
    """
    if not potential_indications:
        return {}

    result: Dict[str, List[str]] = {}

    for group, items in potential_indications.items():
        new_items: List[str] = []
        for raw in items or []:
            base = str(raw or "").strip()
            if not base:
                continue

            # skip if it already looks like a question
            if _looks_like_question(base):
                new_items.append(base)
                continue

            prompt = f"""
You are helping a holistic health practitioner build a checkbox questionnaire.

Input statement (clinical/physiology style):
\"\"\"{base}\"\"\"

Task: Rewrite this as ONE short, clear yes/no **symptom question** that a practitioner can ask a client.
- Use everyday language (bloating, indigestion, dizziness, ringing in the ears, etc.).
- Focus on what the client FEELS or EXPERIENCES, not anatomy.
- Do NOT explain physiology.
- Keep it under 18 words.
- Return ONLY the question sentence, no bullets, no quotes, no commentary.
"""

            try:
                resp = await generate(prompt)
            except Exception:
                resp = base

            line = resp.strip().splitlines()[0].strip()
            if line and not line.endswith("?"):
                line = line.rstrip(".") + "?"
            new_items.append(line or base)

        result[group] = new_items

    return result


# --------------------------------------------------------------------
#  Deterministic analysis sections used by /checkup/analyze
# --------------------------------------------------------------------


async def run_analysis_sections(
        *,
        rah_ids: List[float],
        combination: str,
        analysis_blurb: str,
        selected_ids: List[str],
        notes: str,
        recommendations: str,
        questions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Deterministic analysis that composes sections from:
      • the 3 physiology IDs
      • curated combination/analysis text
      • practitioner selections (checkboxes) + notes
      • triad-level recommendations blob (parsed to buckets)
    """

    names = [
        PHYSIO_LABELS.get(float(x), f"RAH {float(x):.2f}")
        for x in sorted(float(v) for v in (rah_ids or []))
    ]
    correlated = _bullets(
        names + ([f"Interaction: {', '.join(names)}"] if names else [])
    )

    selected_by_group = _selected_texts(questions or [], selected_ids or [])
    indications: List[str] = []
    for grp in ("Physical", "Psychological/Emotional", "Functional"):
        arr = selected_by_group.get(grp, [])
        if arr:
            indications.append(f"**{grp}**")
            indications.extend(arr)

    note_synthesis = (notes or "").strip()
    diagnostic_summary = (analysis_blurb or "").strip() or (
        f"Based on RAH {', '.join(f'{x:.2f}' for x in rah_ids)}, there may be interplay across "
        f"{', '.join(names[:-1])} and {names[-1]}."
        if names
        else "Combination analysis is pending."
    )

    rec = _recommendations_from_text(recommendations or "")

    return {
        "correlated_systems": correlated,
        "indications": _bullets(indications),
        "note_synthesis": note_synthesis,
        "diagnostic_summary": diagnostic_summary,
        "recommendations": {
            "lifestyle": rec.get("lifestyle", []),
            "nutritional": rec.get("nutritional", []),
            "emotional": rec.get("emotional", []),
            "bioresonance": rec.get("bioresonance", []),
            "follow_up": rec.get("follow_up", []),
        },
    }
