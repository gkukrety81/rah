import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function Login() {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const navigate = useNavigate();
    const loc = useLocation() as any;

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setErr(null);
        setBusy(true);
        try {
            const r = await fetch(`${API}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            if (!r.ok) {
                const j = await r.json().catch(() => ({}));
                throw new Error(j.detail || "Login failed");
            }
            const j = await r.json();
            localStorage.setItem("token", j.access_token);

            // notify shell & redirect
            window.dispatchEvent(new Event("auth-changed"));
            const to = loc.state?.from?.pathname || "/";
            navigate(to, { replace: true });
        } catch (e: any) {
            setErr(e.message || "Login error");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100">
            <form
                onSubmit={onSubmit}
                className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
                <h1 className="text-xl font-semibold text-slate-900 mb-4">Sign in</h1>

                <label className="block text-sm text-slate-600 mb-1">Username</label>
                <input
                    className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"/>

                <label className="block text-sm text-slate-600 mb-1">Password</label>
                <input
                    type="password"
                    className="mb-4 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"/>

                {err && <div className="mb-3 text-sm text-red-600">{err}</div>}

                <button
                    type="submit"
                    disabled={busy}
                    className="w-full rounded-lg bg-sky-600 py-2 font-medium text-white hover:bg-sky-700 disabled:opacity-60">
                    {busy ? "Signing in…" : "Sign in"}
                </button>
            </form>
        </div>
    );
}
