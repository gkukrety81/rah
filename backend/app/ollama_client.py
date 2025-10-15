# app/ollama_client.py
import os
import json
import httpx

# Always read from env (docker-compose.yml sets this)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
GEN_MODEL = os.getenv("GEN_MODEL", "llama3.1:8b")

def to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

async def ollama_embed(text: str, model: str | None = None) -> list[float]:
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    payload = {"model": model or EMBED_MODEL, "prompt": text}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["embedding"]

async def ollama_generate(prompt: str, system: str | None = None, model: str | None = None) -> str:
    """
    Stream-parse Ollama /api/generate (returns many JSON objects).
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {"model": model or GEN_MODEL, "prompt": prompt}
    if system:
        payload["system"] = system

    out = ""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload) as r:
            r.raise_for_status()
            async for chunk in r.aiter_text():
                for line in chunk.splitlines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        out += obj.get("response", "")
                    except json.JSONDecodeError:
                        # ignore partial lines
                        continue
    return out.strip()
