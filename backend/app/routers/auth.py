# app/routers/auth.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from ..db import SessionLocal
from ..models import UserAccount
from argon2 import PasswordHasher, exceptions as aex
from ..auth_utils import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])  # 👈 add prefix & tag
ph = PasswordHasher()

class LoginIn(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(body: LoginIn):
    async with SessionLocal() as s:
        res = await s.execute(select(UserAccount).where(
            UserAccount.username == body.username,
            UserAccount.deleted_at.is_(None),
            UserAccount.is_active == True
        ))
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        try:
            ph.verify(user.password_argon2, body.password)
        except aex.VerifyMismatchError:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_access_token(str(user.user_id))
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "user_id": str(user.user_id),
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        }

@router.get("/me")
async def me(user: UserAccount = Depends(get_current_user)):
    return {
        "user_id": str(user.user_id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name
    }
