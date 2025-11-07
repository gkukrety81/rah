// frontend/src/api.ts
// Base URL + auth helper
export const API =
    (import.meta as any).env?.VITE_API_BASE || "http://localhost:8000";

export function authHeaders() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}
export async function getCheckupCase(caseId: string) {
    return fetchJson(`/checkup/${caseId}`);
}

async function fetchJson(input: RequestInfo, init?: RequestInit) {
    const r = await fetch(input, init);
    if (!r.ok) {
        const text = await r.text().catch(() => "");
        throw new Error(`HTTP ${r.status} ${r.statusText} ${text}`);
    }
    return r.json();
}

/* ========= RAH ========= */

export async function getRahPage(page = 1, page_size = 25) {
    return fetchJson(
        `${API}/rah?page=${encodeURIComponent(page)}&page_size=${encodeURIComponent(
            page_size
        )}`,
        { headers: { ...authHeaders() } }
    );
}

/* ========= Auth (if you use them elsewhere) ========= */

export async function login(username: string, password: string) {
    return fetchJson(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    });
}

export async function me() {
    return fetchJson(`${API}/auth/me`, { headers: { ...authHeaders() } });
}

/* ========= Checkup (Stage 1–5) ========= */

// Stage 1: start checkup with three RAH IDs
export async function startCheckup(rah_ids: number[]) {
    return fetchJson(`${API}/checkup/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ rah_ids }),
    });
}

export async function saveAnswers(case_id: string, selected: string[], notes: string) {
    return fetchJson(`${API}/checkup/answers`, {
        method: "POST",
        body: JSON.stringify({ case_id, selected, notes }),
    });
}

export async function listCases(limit = 25) {
    const r = await fetch(`${import.meta.env.VITE_API}/checkup/history?limit=${limit}`, {
        credentials: "include",
    });
    if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`);
    return r.json();
}

export async function translateMarkdown(text: string, target_lang = "de") {
    const r = await fetch(`${import.meta.env.VITE_API}/ai/translate`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, target_lang }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`);
    return r.json();
}

// Stage 3: save selected answers + practitioner notes
export async function saveCheckupAnswers(
    case_id: string,
    answers: string[],
    notes: string
) {
    return fetchJson(`${API}/checkup/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ case_id, answers, notes }),
    });
}

// Stage 4: run AI analysis -> markdown
export async function analyzeCheckup(case_id: string) {
    return fetchJson(`${API}/checkup/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ case_id }),
    });
}

// Open an existing case (for history)
export async function fetchCase(case_id: string) {
    return fetchJson(`${API}/checkup/${encodeURIComponent(case_id)}`, {
        headers: { ...authHeaders() },
    });
}

// History list
export async function listCheckups(limit = 25, offset = 0) {
    return fetchJson(`${API}/checkup?limit=${limit}&offset=${offset}`, {
        headers: { ...authHeaders() },
    });
}

// add this helper to wrap analyze with a 404-repair
export async function analyzeCheckupWithRepair(
    caseId: string,
    rahIds: number[],
    ensureStarted: () => Promise<string> // callback that (re)starts and returns fresh case_id
) {
    try {
        return await analyzeCheckup(caseId);
    } catch (e: any) {
        // If backend says the case doesn't exist, (re)start and retry once
        const msg = (e?.message || "").toLowerCase();
        const body = (e?.bodyText || "");
        if (msg.includes("404") || body.includes("Unknown case_id")) {
            const newCaseId = await ensureStarted();
            return await analyzeCheckup(newCaseId);
        }
        throw e;
    }
}

// Translate Stage 4/5 markdown (e.g., to German)
export async function translateCheckup(caseId: string, lang = "de") {
    return fetchJson(`${API}/checkup/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ case_id: caseId, target_lang: lang }),
    });
}

/* ========= (Optional) other existing API helpers can live here ========= */
export async function downloadCheckupPdf(caseId: string): Promise<Blob> {
    const res = await fetch(`/api/checkup/report/${caseId}/pdf`, {
        method: "GET",
    });
    if (!res.ok) {
        throw new Error(`PDF download failed: ${res.status}`);
    }
    return await res.blob();
}
