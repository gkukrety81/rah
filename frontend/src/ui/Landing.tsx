// frontend/src/ui/Landing.tsx
import React, { useEffect, useState } from "react";
import { aiAnalyze, aiRefreshEmbeddings } from "../api";

const API = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}

type RahRow = {
    rah_id: number;
    details?: string;
    category?: string;
    has_description: boolean;
};

function Chat() {
    const [prompt, setPrompt] = useState(
        "dizziness, ringing in the ears, balance issues"
    );
    const [topK, setTopK] = useState(5);
    const [busy, setBusy] = useState(false);
    const [resp, setResp] = useState<any>(null);
    const [err, setErr] = useState<string | null>(null);

    async function send() {
        setBusy(true);
        setErr(null);
        setResp(null);
        try {
            const data = await aiAnalyze(prompt.trim(), topK);
            setResp(data);
        } catch (e: any) {
            setErr(e.message ?? String(e));
        } finally {
            setBusy(false);
        }
    }

    async function refreshEmbeds() {
        setBusy(true);
        setErr(null);
        try {
            const data = await aiRefreshEmbeddings(); // POST /ai/refresh-embeddings
            setResp({ refreshed: data.updated });
        } catch (e: any) {
            setErr(e.message ?? String(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 12 }}>
            <h3>AI Chat</h3>
            <textarea
                rows={5}
                style={{ width: "100%" }}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe symptoms, e.g. 'dizziness, ringing in the ears, balance issues'"
            />
            <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                <label>
                    Top K:&nbsp;
                    <input
                        type="number"
                        min={1}
                        max={20}
                        value={topK}
                        onChange={(e) => setTopK(Number(e.target.value))}
                        style={{ width: 64 }}
                    />
                </label>
                <button onClick={send} disabled={busy}>
                    {busy ? "Working..." : "Ask"}
                </button>
                <button onClick={refreshEmbeds} disabled={busy} title="Recompute missing/changed embeddings">
                    Refresh Embeddings
                </button>
            </div>

            {err && (
                <pre style={{ whiteSpace: "pre-wrap", color: "crimson", marginTop: 8 }}>
          {err}
        </pre>
            )}
            {resp && (
                <pre style={{ whiteSpace: "pre-wrap", marginTop: 8, background: "#f6f6f6", padding: 8 }}>
          {JSON.stringify(resp, null, 2)}
        </pre>
            )}
        </div>
    );
}

export default function Landing() {
    const [list, setList] = useState<RahRow[]>([]);
    const [rahId, setRahId] = useState<string>("58.41");
    const [details, setDetails] = useState<string>("Semicircular canals");
    const [category, setCategory] = useState<string>("Acoustic organ");
    const [busy, setBusy] = useState<boolean>(false);
    const [err, setErr] = useState<string | null>(null);

    async function load() {
        setErr(null);
        try {
            const r = await fetch(`${API}/rah`, { headers: { ...authHeaders() } });
            if (!r.ok) throw new Error(`Load failed: ${r.status} ${await r.text()}`);
            const j = await r.json();
            setList(j);
        } catch (e: any) {
            setErr(e.message ?? String(e));
        }
    }

    async function createRah() {
        setBusy(true);
        setErr(null);
        try {
            const r = await fetch(`${API}/rah`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify({
                    rah_id: parseFloat(rahId),
                    details,
                    category,
                    auto_generate: false,
                }),
            });
            if (!r.ok) throw new Error(`Create failed: ${r.status} ${await r.text()}`);
            await load();
        } catch (e: any) {
            setErr(e.message ?? String(e));
        } finally {
            setBusy(false);
        }
    }

    useEffect(() => {
        load();
    }, []);

    return (
        <div
            style={{
                display: "grid",
                gap: 16,
                gridTemplateColumns: "1fr 1fr",
                alignItems: "start",
            }}
        >
            <Chat />

            <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 12 }}>
                <h3>RAH IDs</h3>

                <div style={{ display: "grid", gap: 8, gridTemplateColumns: "auto 1fr" }}>
                    <label>RAH ID:</label>
                    <input value={rahId} onChange={(e) => setRahId(e.target.value)} />

                    <label>Details:</label>
                    <input value={details} onChange={(e) => setDetails(e.target.value)} />

                    <label>Category:</label>
                    <input value={category} onChange={(e) => setCategory(e.target.value)} />
                </div>

                <button onClick={createRah} disabled={busy} style={{ marginTop: 10 }}>
                    {busy ? "Saving..." : "Create"}
                </button>

                {err && (
                    <pre style={{ whiteSpace: "pre-wrap", color: "crimson", marginTop: 8 }}>
            {err}
          </pre>
                )}

                <table border={1} cellPadding={6} style={{ marginTop: 16, width: "100%" }}>
                    <thead>
                    <tr>
                        <th>RAH ID</th>
                        <th>Details</th>
                        <th>Category</th>
                        <th>Description?</th>
                    </tr>
                    </thead>
                    <tbody>
                    {list.map((r) => (
                        <tr key={r.rah_id}>
                            <td>{r.rah_id.toFixed(2)}</td>
                            <td>{r.details}</td>
                            <td>{r.category}</td>
                            <td>{r.has_description ? "Yes" : "No"}</td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
