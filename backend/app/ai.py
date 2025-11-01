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
# --- Adapter for checkup.py ---
async def run_analysis_sections(rah_ids, combination, analysis_blurb, selected_ids, notes, recommendations):
    """
    Adapter wrapper so checkup.py can call AI analysis uniformly.
    Adjust this if you already have another core AI function.
    """
    # If your existing AI analysis is in another function (like run_analysis),
    # just forward the arguments to it. For example:
    #
    # sections = await run_analysis(...)
    #
    # For now, return a minimal empty structure to unblock API startup:
    return {
        "correlated_systems": [],
        "indications": [],
        "note_synthesis": "",
        "diagnostic_summary": "",
        "recommendations": {
            "lifestyle": [],
            "nutritional": [],
            "emotional": [],
            "bioresonance": [],
            "follow_up": [],
        },
    }
