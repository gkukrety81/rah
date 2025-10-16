import React, { useState } from "react";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}

export default function Landing() {
    const [prompt, setPrompt] = useState(
        "fatigue, headaches, swelling in feet"
    );
    const [resp, setResp] = useState<string>("");

    async function ask() {
        setResp("Thinking…");
        const r = await fetch(`${API}/ai/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ prompt, top_k: 5 }),
        });
        const j = await r.json();
        setResp(JSON.stringify(j, null, 2));
    }

    return (
        <div className="space-y-4">
            <h2 className="text-xl font-semibold">AI Chat</h2>
            <textarea
                className="w-full rounded-md border p-3"
                rows={4}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
            />
            <div>
                <button
                    onClick={ask}
                    className="px-4 py-2 rounded-md bg-indigo-600 text-white hover:bg-indigo-700"
                >
                    Ask
                </button>
            </div>
            <pre className="whitespace-pre-wrap rounded-md border bg-white p-3">
        {resp}
      </pre>
        </div>
    );
}
