const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function authHeader() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function aiAnalyze(prompt: string, top_k = 5) {
    const res = await fetch(`${API}/ai/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ prompt, top_k }),
    });
    if (!res.ok) throw new Error(`AI analyze failed: ${res.status} ${await res.text()}`);
    return res.json();
}

export async function aiRefreshEmbeddings() {
    const res = await fetch(`${API}/ai/refresh-embeddings`, {
        method: "POST",
        headers: { ...authHeader() },
    });
    if (!res.ok) throw new Error(`Refresh failed: ${res.status} ${await res.text()}`);
    return res.json();
}

export async function authLogin(username: string, password: string) {
    const res = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`);
    return res.json();
}

export function setToken(tok: string) {
    localStorage.setItem("token", tok);
}
