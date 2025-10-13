from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import insert, select
from ..db import SessionLocal
from ..models import PhysiologyProgram

router = APIRouter()

class ProgramIn(BaseModel):
    program_code: int
    name: str
    sex: str = "unisex"

@router.post("")
async def create_program(p: ProgramIn):
    async with SessionLocal() as s:
        stmt = insert(PhysiologyProgram).values(program_code=p.program_code, name=p.name, sex=p.sex)
        try:
            await s.execute(stmt)
            await s.commit()
        except Exception as e:
            await s.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

@router.get("")
async def list_programs():
    async with SessionLocal() as s:
        res = await s.execute(select(PhysiologyProgram))
        rows = res.scalars().all()
        return [{"program_code": r.program_code, "name": r.name, "sex": r.sex} for r in rows]
