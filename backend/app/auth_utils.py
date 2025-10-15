import os, datetime
from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from .db import SessionLocal, get_session
from .models import UserAccount
from sqlalchemy.ext.asyncio import AsyncSession

SECRET = os.getenv("JWT_SECRET", "change_me")
ALGO = "HS256"
EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "12"))

def create_access_token(sub: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + datetime.timedelta(hours=EXPIRE_HOURS)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)

bearer = HTTPBearer(auto_error=False)

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = creds.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with SessionLocal() as s:
        res = await s.execute(select(UserAccount).where(UserAccount.user_id==sub, UserAccount.deleted_at.is_(None), UserAccount.is_active==True))
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user
