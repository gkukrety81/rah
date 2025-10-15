from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_session
from ..models import UserAccount

router = APIRouter(prefix="/users", tags=["users"])  # ✅ Add prefix

class UserIn(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    branch: str
    location: str
    password: str

@router.post("/")  # ✅ non-empty path
async def create_user(u: UserIn, session: AsyncSession = Depends(get_session)):
    stmt = insert(UserAccount).values(
        first_name=u.first_name,
        last_name=u.last_name,
        username=u.username,
        email=u.email,
        branch=u.branch,
        location=u.location,
        password_argon2=u.password,
    )
    try:
        await session.execute(stmt)
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

@router.get("/")  # ✅ non-empty path
async def list_users(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(UserAccount).order_by(UserAccount.user_id))
    rows = res.scalars().all()
    return [
        {
            "user_id": r.user_id,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "username": r.username,
            "email": r.email,
            "branch": r.branch,
            "location": r.location,
            "is_active": r.is_active,
        }
        for r in rows
    ]
