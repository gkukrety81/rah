from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import rah, programs, users, auth, ai

app = FastAPI(title="RAH AI Knowledge System API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(rah.router, prefix="/rah", tags=["rah"])
app.include_router(programs.router, prefix="/programs", tags=["programs"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])

@app.get("/healthz")
async def healthz():
    return {"ok": True}