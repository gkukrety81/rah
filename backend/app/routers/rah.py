# app/routers/rah.py
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, delete, insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_session
from ..models import RahItem
from ..ollama_client import ollama_generate

router = APIRouter(prefix="/rah", tags=["rah"])

class RahIn(BaseModel):
    rah_id: float
    details: str
    category: str
    description: str | None = None
    generate: bool = True  # auto-generate description if not provided

def _desc_preview(s: str | None) -> bool:
    return bool(s and s.strip())

@router.get("")
async def list_rah(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=200),
        q: str | None = None,
        session: AsyncSession = Depends(get_session),
):
    where = []
    stmt_count = select(func.count()).select_from(RahItem)
    stmt_rows = select(RahItem).order_by(RahItem.rah_id)

    if q:
        like = f"%{q.strip()}%"
        from sqlalchemy import or_
        where.append(or_(RahItem.details.ilike(like),
                         RahItem.category.ilike(like)))

    if where:
        stmt_count = stmt_count.where(*where)
        stmt_rows = stmt_rows.where(*where)

    total = (await session.execute(stmt_count)).scalar_one()
    offset = (page - 1) * page_size
    rows = (await session.execute(stmt_rows.limit(page_size).offset(offset))).scalars().all()

    items = [{
        "rah_id": float(r.rah_id),
        "details": r.details,
        "category": r.category,
        "has_description": _desc_preview(r.description)
    } for r in rows]

    pages = (total + page_size - 1) // page_size
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": pages}

@router.post("")
async def create_rah(body: RahIn, session: AsyncSession = Depends(get_session)):
    # upsert (create or replace)
    await session.execute(
        insert(RahItem)
        .values(
            rah_id=body.rah_id,
            details=body.details,
            category=body.category,
            description=body.description or None
        )
        .on_conflict_do_update(
            index_elements=[RahItem.rah_id],
            set_={
                "details": body.details,
                "category": body.category,
                "description": body.description or None,
            },
        )
    )
    # auto-generate description if requested and missing
    if (body.generate is True) and not body.description:
        prompt = (
            "Write a structured medical narrative (~1000 words) for the following RAH item. "
            "Use clear sections: Overview, Physiology/Mechanism, Clinical Presentation, "
            "Differential Considerations, Assessment, and Supportive/Therapeutic Notes. "
            f"\n\nName: {body.details}\nCategory: {body.category}\n"
        )
        try:
            narrative = await ollama_generate(prompt)
            await session.execute(
                update(RahItem)
                .where(RahItem.rah_id == body.rah_id)
                .values(description=narrative)
            )
        except Exception:
            # keep insert successful even if generation fails
            pass

    await session.commit()
    return {"ok": True}

@router.delete("/{rah_id}")
async def delete_rah(rah_id: float, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(RahItem).where(RahItem.rah_id == rah_id))
    await session.commit()
    return {"ok": True}

@router.get("")
async def list_rah(limit: int = 25, offset: int = 0):
    async with SessionLocal() as s:
        total = (await s.execute(sa_text("SELECT COUNT(*) FROM rah_schema.rah_item"))).scalar_one()
        res = await s.execute(
            select(RahItem).order_by(RahItem.rah_id).limit(limit).offset(offset)
        )
        items = res.scalars().all()
        return {
            "items": [
                {
                    "rah_id": float(i.rah_id),
                    "details": i.details,
                    "category": i.category,
                    "has_description": bool(i.description),
                }
                for i in items
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
