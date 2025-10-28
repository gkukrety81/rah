# backend/app/routers/rah.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_session
from ..models import RahItem

router = APIRouter(prefix="/rah", tags=["rah"])


@router.get("/{rah_id}/description")
async def get_description(rah_id: float, session: AsyncSession = Depends(get_session)):
    r = await session.execute(
        sa_text("SELECT details, description FROM rah_schema.rah_item WHERE rah_id=:x"), {"x": rah_id}
    )
    row = r.first()
    if not row:
        raise HTTPException(404, "Not found")
    details, description = row
    return {
        "rah_id": rah_id,
        "title": details or "",
        "description": (description or "").strip()
    }

@router.get("")
async def list_rah(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
):
    # total first
    total = (await session.execute(select(func.count()).select_from(RahItem))).scalar_one()

    # data page
    q = (
        select(RahItem)
        .order_by(RahItem.rah_id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await session.execute(q)).scalars().all()

    items = [{
        "rah_id": float(r.rah_id),
        "details": r.details,
        "category": r.category,
        "has_description": bool(r.description),
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
