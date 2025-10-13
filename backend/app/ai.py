import os, httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
GEN_MODEL = os.getenv("GEN_MODEL", "llama3.1:8b")

async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{OLLAMA_BASE}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text})
        r.raise_for_status()
        return r.json().get("embedding", [])

async def generate(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(f"{OLLAMA_BASE}/api/generate", json={"model": GEN_MODEL, "prompt": prompt, "stream": False})
        r.raise_for_status()
        j = r.json()
        return j.get("response", "")