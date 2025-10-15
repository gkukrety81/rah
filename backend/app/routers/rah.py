from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import insert, select, update, delete
from ..db import SessionLocal
from ..models import RahItem, PhysiologyProgram, RahItemProgram, CorpusDoc, CorpusChunk
import math

router = APIRouter(
    prefix="/rah",
    tags=["rah"]
)

class RahIn(BaseModel):
    rah_id: float
    details: str | None = None
    category: str | None = None
    auto_generate: bool = True

class RahEdit(BaseModel):
    details: str | None = None
    category: str | None = None
    description: str | None = None

def floor_program_code(rah_id: float) -> int:
    return int(math.floor(rah_id))

async def ensure_program_mapping(session, rah_id: float):
    code = floor_program_code(rah_id)
    prog = await session.execute(select(PhysiologyProgram).where(PhysiologyProgram.program_code == code))
    pobj = prog.scalar_one_or_none()
    if not pobj:
        await session.execute(insert(PhysiologyProgram).values(program_code=code, name=f"Program {code}.00", sex="unisex"))
    exists = await session.execute(select(RahItemProgram).where(RahItemProgram.rah_id==rah_id, RahItemProgram.program_code==code))
    if not exists.scalar_one_or_none():
        await session.execute(insert(RahItemProgram).values(rah_id=rah_id, program_code=code))

@router.post("/")
async def create_rah(item: RahIn):
    async with SessionLocal() as s:
        try:
            await s.execute(insert(RahItem).values(rah_id=item.rah_id, details=item.details, category=item.category))
            await ensure_program_mapping(s, item.rah_id)
            await s.commit()
        except Exception as e:
            await s.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "rah_id": item.rah_id}

@router.get("/{rah_id}")
async def get_rah(rah_id: float):
    async with SessionLocal() as s:
        r = await s.execute(select(RahItem).where(RahItem.rah_id==rah_id))
        item = r.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        p = await s.execute(select(RahItemProgram, PhysiologyProgram).join(PhysiologyProgram, RahItemProgram.program_code==PhysiologyProgram.program_code).where(RahItemProgram.rah_id==rah_id))
        programs = [{"program_code": row.PhysiologyProgram.program_code, "name": row.PhysiologyProgram.name} for row in p]
        return {
            "rah_id": float(item.rah_id),
            "details": item.details,
            "category": item.category,
            "description": item.description,
            "programs": programs
        }

@router.get("/")
async def list_rah(limit: int = 100, offset: int = 0):
    async with SessionLocal() as s:
        res = await s.execute(select(RahItem).order_by(RahItem.rah_id).limit(limit).offset(offset))
        items = res.scalars().all()
        return [{
            "rah_id": float(i.rah_id),
            "details": i.details,
            "category": i.category,
            "has_description": bool(i.description)
        } for i in items]

@router.put("/{rah_id}")
async def update_rah(rah_id: float, patch: RahEdit):
    async with SessionLocal() as s:
        r = await s.execute(select(RahItem).where(RahItem.rah_id==rah_id))
        item = r.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        vals = {}
        if patch.details is not None: vals["details"] = patch.details
        if patch.category is not None: vals["category"] = patch.category
        if patch.description is not None: vals["description"] = patch.description
        if vals:
            await s.execute(update(RahItem).where(RahItem.rah_id==rah_id).values(**vals))
        await s.commit()
    return {"ok": True}

@router.delete("/{rah_id}")
async def delete_rah(rah_id: float):
    async with SessionLocal() as s:
        await s.execute(delete(RahItem).where(RahItem.rah_id==rah_id))
        await s.commit()
    return {"ok": True}
