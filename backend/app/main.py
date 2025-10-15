from fastapi import FastAPI
from .routers import ai, rah, programs, users, auth, debug  # include ai here

app = FastAPI(title="RAH API")

# Routers
app.include_router(ai.router)
app.include_router(rah.router)
app.include_router(programs.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(debug.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
