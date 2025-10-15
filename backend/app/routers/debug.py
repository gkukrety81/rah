from fastapi import APIRouter
import httpx, os

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/ollama")
async def debug_ollama():
    base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}/api/tags")
            r.raise_for_status()
            return {"ok": True, "base_url": base, "len": len(r.text)}
    except Exception as e:
        return {"ok": False, "base_url": base, "error": str(e)}
