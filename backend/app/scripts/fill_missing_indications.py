# backend/app/scripts/fill_missing_indications.py
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Any

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal  # same pattern as your other scripts


# -------------------------------------------------------------------
# 1. Deterministic templates: per-physiology, per group
#    Keys are the official 21 RAH physiology codes.
# -------------------------------------------------------------------

TEMPLATES: Dict[float, Dict[str, List[str]]] = {
    30.00: {  # Cells & tissue
        "Physical": [
            "Do you bruise easily or notice delayed wound healing?",
            "Do you experience persistent fatigue or general bodily weakness?",
        ],
        "Functional": [
            "Do you have chronic aches or pains without a clear medical cause?",
        ],
    },
    32.00: {  # Blood
        "Physical": [
            "Do you often feel light-headed or dizzy when standing up quickly?",
            "Do you experience cold hands or feet or notice that your skin looks pale?",
        ],
        "Functional": [
            "Have you ever been told you have low iron or anemia?",
        ],
    },
    34.00: {  # Immune system
        "Physical": [
            "Do you catch colds or infections more frequently than people around you?",
            "Do minor infections or wounds take a long time to clear up?",
        ],
        "Psychological/Emotional": [
            "Do you feel run down or depleted after even minor illnesses?",
        ],
    },
    36.00: {  # Lymphatic system
        "Physical": [
            "Do you experience swelling in your ankles, legs, fingers, or around the eyes?",
            "Do you feel heavy or congested in your body, especially in the mornings?",
        ],
        "Functional": [
            "Do you notice tenderness or discomfort along the neck, armpit, or groin areas?",
        ],
    },
    38.00: {  # Circulatory system
        "Physical": [
            "Do you experience shortness of breath on mild exertion such as climbing stairs?",
            "Do you often have cold hands or feet even in warm environments?",
        ],
        "Functional": [
            "Do your legs ache, feel heavy, or show prominent veins after standing for long periods?",
        ],
    },
    40.00: {  # Heart
        "Physical": [
            "Do you feel palpitations, skipped beats, or a racing heart at rest or with mild effort?",
            "Do you get chest tightness, pressure, or discomfort during exertion or stress?",
        ],
        "Functional": [
            "Do you tire easily when walking uphill or climbing a single flight of stairs?",
        ],
    },
    42.00: {  # Respiratory system
        "Physical": [
            "Do you often feel short of breath or tight in the chest?",
            "Do you have a chronic cough, wheeze, or frequent mucus in the airways?",
        ],
        "Functional": [
            "Do you struggle to take a deep, satisfying breath, especially during activity?",
        ],
    },
    44.00: {  # Kidney / urinary
        "Physical": [
            "Do you need to urinate very frequently or urgently during the day?",
            "Do you experience burning, discomfort, or pain when passing urine?",
        ],
        "Functional": [
            "Do you wake more than once a night to pass urine?",
        ],
    },
    46.00: {  # Digestive system
        "Physical": [
            "Do you often feel bloated or gassy after meals?",
            "Do you experience indigestion, heartburn, or acid reflux?",
        ],
        "Functional": [
            "Do you have irregular bowel movements, such as constipation or loose stools?",
        ],
    },
    48.00: {  # Liver – gall – pancreas
        "Physical": [
            "Do you feel heavy, full, or nauseous after fatty or rich foods?",
            "Do you experience discomfort or pain under the right rib cage or upper abdomen?",
        ],
        "Functional": [
            "Do you notice swings in energy or shakiness if you go a long time without eating?",
        ],
    },
    50.00: {  # Metabolism
        "Physical": [
            "Have you noticed unexplained weight gain or difficulty losing weight?",
            "Do you feel sluggish or tired even after what should be adequate sleep?",
        ],
        "Functional": [
            "Do you often feel unusually hot or cold compared with other people in the same environment?",
        ],
    },
    52.00: {  # Musculoskeletal
        "Physical": [
            "Do you have frequent joint or muscle pain or stiffness?",
            "Do you experience back, neck, or shoulder tension on most days?",
        ],
        "Functional": [
            "Do you feel restricted in movement or flexibility during everyday tasks?",
        ],
    },
    54.00: {  # Nervous system
        "Physical": [
            "Do you experience tingling, numbness, or 'pins and needles' in your hands or feet?",
        ],
        "Psychological/Emotional": [
            "Do you struggle with concentration, memory, or mental clarity?",
            "Do you feel easily overstimulated by noise, light, or stressful environments?",
        ],
    },
    56.00: {  # Vision
        "Physical": [
            "Do you have frequent eye strain, dryness, or headaches after screen use or reading?",
            "Do you notice blurred or fluctuating vision during the day?",
        ],
        "Functional": [
            "Do you find night-time or low-light vision particularly challenging?",
        ],
    },
    58.00: {  # Acoustic / equilibrium
        "Physical": [
            "Do you experience ringing in the ears (tinnitus) or reduced hearing?",
        ],
        "Functional": [
            "Do you suffer from dizziness, vertigo, or a sensation that the room is spinning?",
        ],
        "Psychological/Emotional": [
            "Do you worry about losing balance or falling during everyday activities?",
        ],
    },
    62.00: {  # Skin / hair
        "Physical": [
            "Do you have dry, itchy, or easily irritated skin?",
            "Have you noticed unusual hair loss, thinning, or brittle nails?",
        ],
        "Functional": [
            "Do your skin or scalp symptoms flare up with certain foods, products, or stress?",
        ],
    },
    64.00: {  # Hormonal system
        "Physical": [
            "Do you notice cyclical headaches, breast tenderness, or fluid retention?",
        ],
        "Psychological/Emotional": [
            "Do your mood and energy fluctuate strongly with your cycle or time of day?",
        ],
        "Functional": [
            "Do you experience hot flushes, night sweats, or sudden temperature changes?",
        ],
    },
    66.00: {  # Female sexual organs
        "Physical": [
            "Do you have painful, heavy, or irregular menstrual periods?",
        ],
        "Functional": [
            "Do you experience pelvic discomfort, vaginal dryness, or pain with intercourse?",
        ],
        "Psychological/Emotional": [
            "Do hormonal or cycle changes significantly affect your mood or sleep?",
        ],
    },
    68.00: {  # Male sexual organs
        "Physical": [
            "Do you experience reduced libido or difficulty maintaining an erection?",
        ],
        "Functional": [
            "Do you notice urinary hesitancy, weak flow, or needing to strain when passing urine?",
        ],
        "Psychological/Emotional": [
            "Do concerns about sexual performance impact your confidence or relationships?",
        ],
    },
    72.00: {  # Psyche
        "Psychological/Emotional": [
            "Do you often feel anxious, low, or emotionally overwhelmed?",
            "Do you have difficulty relaxing or 'switching off' mentally?",
        ],
        "Functional": [
            "Do emotional stresses significantly affect your sleep, digestion, or energy levels?",
        ],
    },
    75.00: {  # Stress
        "Physical": [
            "Do you feel wired-and-tired, tense, or restless much of the time?",
        ],
        "Psychological/Emotional": [
            "Do you feel under constant pressure or find it hard to recover from stress?",
        ],
        "Functional": [
            "Do stressful periods trigger headaches, digestive upset, or flare-ups of existing symptoms?",
        ],
    },
    76.00: {  # Teeth (overall)
        "Physical": [
            "Do you have tooth sensitivity, pain, or bleeding gums?",
        ],
        "Functional": [
            "Do you clench or grind your teeth at night or when stressed?",
        ],
        "Psychological/Emotional": [
            "Do dental issues affect your confidence when eating, speaking, or smiling?",
        ],
    },
}


GROUPS = ("Physical", "Psychological/Emotional", "Functional")


# -------------------------------------------------------------------
# 2. Helpers
# -------------------------------------------------------------------

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in items:
        s_clean = str(s).strip()
        if not s_clean or s_clean in seen:
            continue
        seen.add(s_clean)
        out.append(s_clean)
    return out


def build_questions_for_triad(codes: List[float]) -> Dict[str, List[str]]:
    """
    Given three physiology codes (e.g. [42.0, 46.0, 58.0]),
    merge template questions from each code into a single
    {Physical / Psychological/Emotional / Functional} structure.
    """
    result: Dict[str, List[str]] = {g: [] for g in GROUPS}

    for raw in codes:
        code = float(raw)
        tpl = TEMPLATES.get(code)
        if not tpl:
            continue
        for group, qs in tpl.items():
            if group not in result:
                result[group] = []
            result[group].extend(qs or [])

    # de-duplicate within each group, keep user-friendly order
    for g in GROUPS:
        result[g] = _dedupe_keep_order(result.get(g, []))

    return result


async def _fetch_empty_triads(session: AsyncSession):
    """
    Find all combinations where potential_indications exists but all 3 arrays are empty.
    """
    res = await session.execute(
        sa_text(
            """
            SELECT combination_id::text, rah_ids
            FROM rah_schema.rah_combination_profiles
            WHERE (
                      COALESCE(jsonb_array_length(potential_indications->'Physical'), 0)
                          + COALESCE(jsonb_array_length(potential_indications->'Psychological/Emotional'), 0)
                          + COALESCE(jsonb_array_length(potential_indications->'Functional'), 0)
                      ) = 0
            ORDER BY combination_id
            """
        )
    )
    return res.fetchall()


async def process_one(session: AsyncSession, combo_id: str, rah_ids: List[Any]) -> None:
    codes = [float(x) for x in rah_ids or []]
    new_pi = build_questions_for_triad(codes)

    # safety: if nothing produced, don't write garbage
    if not any(new_pi.get(g) for g in GROUPS):
        print(f"[fill] WARNING: no templates found for {codes} -> skipping {combo_id}")
        return

    await session.execute(
        sa_text(
            """
            UPDATE rah_schema.rah_combination_profiles
            SET potential_indications = CAST(:pi AS jsonb),
                updated_at            = now()
            WHERE combination_id = CAST(:cid AS uuid)
            """
        ),
        {"pi": json.dumps(new_pi), "cid": combo_id},
    )


# -------------------------------------------------------------------
# 3. Main entry
# -------------------------------------------------------------------

async def main() -> None:
    async with SessionLocal() as session:  # type: ignore[arg-type]
        rows = await _fetch_empty_triads(session)
        total = len(rows)
        print(f"[fill] Found {total} combinations with empty potential_indications")

        if total == 0:
            print("[fill] nothing to do")
            return

        done = 0
        for combo_id, rah_ids in rows:
            done += 1
            print(f"[fill] {done}/{total} -> {combo_id}  rah_ids={rah_ids}")
            try:
                await process_one(session, combo_id, rah_ids)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"[fill] ERROR on {combo_id}: {e!r}")

        print("[fill] completed.")


if __name__ == "__main__":
    asyncio.run(main())
