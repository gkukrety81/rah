const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}

// Dedicated backend endpoint (preferred). Falls back gracefully if missing.
export async function apiCheckup(
    rahIds: number[],
    selectedTicks: string[] = [],
    practitionerNotes: string = ""
) {
    const r = await fetch(`${API_BASE}/ai/checkup`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ rah_ids: rahIds, selected_ticks: selectedTicks, practitioner_notes: practitionerNotes }),
    });

    if (r.status === 404) throw new Error("checkup endpoint not present");
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}

// Fallback using existing /ai/analyze so the page still works before backend is wired.
export async function apiAnalyzeFallback(rahIds: number[]) {
    const text = `Client indicates correlation between RAH IDs: ${rahIds.join(
        ", "
    )}. Please provide short analysis, potential indications and rebalancing guidance.`;

    const r = await fetch(`${API_BASE}/ai/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ prompt: text, top_k: 5 }),
    });

    if (!r.ok) throw new Error(await r.text());
    const j = await r.json();

    // Shape it to our CheckupResult type
    return {
        comboTitle: `RAH ${rahIds.map((n) => n.toFixed(2)).join(" + ")}`,
        analysis: j.explanation ?? "Analysis not available.",
        suggestions: (j.matches ?? []).slice(0, 6).map((m: any) => ({
            group: "Physical",
            text: `${m.details} — ${m.category}`,
        })),
        recommendations:
            "Adopt an integrative plan: regular gentle movement, anti-inflammatory diet, stress reduction, hydration; escalate to specialist referral if red flags persist.",
    };
}
