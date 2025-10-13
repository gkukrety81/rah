from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from argon2 import PasswordHasher
from ..db import SessionLocal
from ..models import UserAccount
from datetime import datetime, timezone

router = APIRouter()
ph = PasswordHasher()

class UserIn(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: EmailStr
    branch: str | None = None
    location: str | None = None
    password: str

class UserOut(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    username: str
    email: EmailStr
    branch: str | None = None
    location: str | None = None
    is_active: bool
    deleted_at: str | None = None

@router.get("")
async def list_users():
    async with SessionLocal() as s:
        res = await s.execute(select(UserAccount).where(UserAccount.deleted_at.is_(None)))
        rows = res.scalars().all()
        return [{
            "user_id": str(r.user_id),
            "first_name": r.first_name,
            "last_name": r.last_name,
            "username": r.username,
            "email": r.email,
            "branch": r.branch,
            "location": r.location,
            "is_active": r.is_active,
            "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None
        } for r in rows]

@router.post("")
async def create_user(u: UserIn):
    pwd_hash = ph.hash(u.password)
    async with SessionLocal() as s:
        # ensure uniqueness on username/email
        res = await s.execute(select(UserAccount).where((UserAccount.username==u.username) | (UserAccount.email==u.email)))
        if res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username or email already exists")
        obj = UserAccount(
            first_name=u.first_name, last_name=u.last_name, username=u.username,
            email=u.email, branch=u.branch, location=u.location, password_argon2=pwd_hash
        )
        s.add(obj)
        await s.commit()
        await s.refresh(obj)
        return {"ok": True, "user_id": str(obj.user_id)}

@router.delete("/{user_id}")
async def soft_delete_user(user_id: str):
    async with SessionLocal() as s:
        res = await s.execute(select(UserAccount).where(UserAccount.user_id==user_id))
        obj = res.scalar_one_or_none()
        if not obj:
            raise HTTPException(status_code=404, detail="User not found")
        await s.execute(update(UserAccount).where(UserAccount.user_id==user_id).values(deleted_at=datetime.now(timezone.utc), is_active=False))
        await s.commit()
        return {"ok": True}
