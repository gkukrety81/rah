from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import ai, rah, programs, users, auth, debug  # include ai here

app = FastAPI(title="RAH API")

# allow your Vite dev server
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,                 # if you ever send cookies; fine to keep on
    allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["Authorization","Content-Type","Accept","X-Requested-With","*"],
)

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
