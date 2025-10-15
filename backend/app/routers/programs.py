# app/routers/programs.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import PhysiologyProgram

router = APIRouter(prefix="/programs", tags=["programs"])  # ✅ non-empty prefix

class ProgramIn(BaseModel):
    program_code: int
    name: str
    sex: str = "unisex"

@router.post("/")  # ✅ non-empty path (relative to /programs)
async def create_program(p: ProgramIn, session: AsyncSession = Depends(get_session)):
    stmt = insert(PhysiologyProgram).values(
        program_code=p.program_code, name=p.name, sex=p.sex
    )
    try:
        await session.execute(stmt)
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

@router.get("/")  # ✅ non-empty path
async def list_programs(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(PhysiologyProgram).order_by(PhysiologyProgram.program_code))
    rows = res.scalars().all()
    return [
        {"program_code": int(r.program_code), "name": r.name, "sex": r.sex}
        for r in rows
    ]
