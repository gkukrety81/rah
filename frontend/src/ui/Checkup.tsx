// frontend/src/ui/Checkup.tsx
import { useMemo, useState } from "react";
import { startCheckup, saveCheckupAnswers, analyzeCheckup } from "../api";

type Question = { id: string; text: string; group: "Physical" | "Psychological/Emotional" | "Functional" };
type StartResp = {
    ok: boolean;
    case_id: string;
    rah_ids: number[];
    combination_title: string;
    analysis_blurb: string;
    questions: Question[];
    recommendations?: string;
    source: "db" | "ai";
};
type AnalyzeResp = { case_id: string; sections: Record<string, any>; markdown: string };

export default function Checkup() {
    // Stage 1 inputs
    const [rah1, setRah1] = useState("00.00");
    const [rah2, setRah2] = useState("00.00");
    const [rah3, setRah3] = useState("00.00");

    // Flow state
    const [busy, setBusy] = useState(false);
    const [caseId, setCaseId] = useState<string | null>(null);
    const [source, setSource] = useState<"db" | "ai">("ai");

    // Stage 2 data
    const [combo, setCombo] = useState("");
    const [blurb, setBlurb] = useState("");
    const [qs, setQs] = useState<Question[]>([]);
    const [selected, setSelected] = useState<string[]>([]);
    const [reco, setReco] = useState<string>("");

    // Stage 3
    const [notes, setNotes] = useState("");

    // Stage 4/5
    const [resultMd, setResultMd] = useState("");

    const grouped = useMemo(() => {
        const g: Record<"Physical" | "Psychological/Emotional" | "Functional", Question[]> = {
            Physical: [],
            "Psychological/Emotional": [],
            Functional: [],
        };
        for (const q of qs) (g[q.group] ?? g.Physical).push(q);
        return g;
    }, [qs]);

    function resetAll() {
        setRah1("00.00"); setRah2("00.00"); setRah3("00.00");
        setBusy(false); setCaseId(null); setSource("ai");
        setCombo(""); setBlurb(""); setQs([]); setSelected([]); setReco("");
        setNotes(""); setResultMd("");
    }

    async function onCheck() {
        setBusy(true);
        try {
            const ids = [parseFloat(rah1), parseFloat(rah2), parseFloat(rah3)];
            const res: StartResp = await startCheckup(ids);
            setCaseId(res.case_id);
            setSource(res.source);
            setCombo(res.combination_title || "");
            setBlurb(res.analysis_blurb || "");
            setQs(Array.isArray(res.questions) ? res.questions : []);
            setReco(res.recommendations || "");
            setSelected([]);
            setResultMd("");
            // scroll to Stage 2
            setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 30);
        } catch (e) {
            console.error(e);
            alert("Check failed");
        } finally {
            setBusy(false);
        }
    }

    async function onAnalyze() {
        if (!caseId) return;
        setBusy(true);
        try {
            await saveCheckupAnswers(caseId, selected, notes);
            const res: AnalyzeResp = await analyzeCheckup(caseId);
            setResultMd(res.markdown || "");
            setTimeout(() => document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }), 40);
        } catch (e) {
            console.error(e);
            alert("AI analysis failed");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="max-w-5xl mx-auto">
            {/* Stage 1: Enter IDs */}
            <div className="bg-white rounded-2xl shadow-sm border">
                <div className="px-6 py-5 border-b flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-violet-100 text-violet-700">⚕️</span>
                        <div>
                            <div className="font-semibold text-lg">RAH check-up</div>
                            <div className="text-gray-500 text-sm">
                                Enter three RAH IDs and click <span className="font-medium">Check</span> to generate questions.
                            </div>
                        </div>
                    </div>
                    <div className="flex gap-3">
                        <button
                            onClick={onCheck}
                            disabled={busy}
                            className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50"
                            title="Generate questionnaire"
                        >
                            ✨ Check
                        </button>
                        <button
                            onClick={resetAll}
                            disabled={busy}
                            className="inline-flex items-center gap-2 rounded-md border px-4 py-2 hover:bg-gray-50 disabled:opacity-50"
                            title="Reset all"
                        >
                            🧹 Reset
                        </button>
                    </div>
                </div>

                <div className="px-6 py-5 bg-slate-50/60">
                    <div className="flex flex-wrap items-center gap-6">
                        <RahInput label="RAH check-up 1" value={rah1} onChange={setRah1} />
                        <RahInput label="RAH check-up 2" value={rah2} onChange={setRah2} />
                        <RahInput label="RAH check-up 3" value={rah3} onChange={setRah3} />
                    </div>
                </div>
            </div>

            {/* Stage 2: Combination + Analysis + Potential Indications + Recommendations */}
            {caseId && (
                <div className="mt-6 bg-white rounded-2xl border overflow-hidden">
                    <div className="px-6 py-5 border-b flex items-center justify-between">
                        <div>
                            <div className="text-sm text-gray-500 uppercase tracking-wide">Combination</div>
                            <div className="text-base font-medium mt-1">{combo || "—"}</div>
                        </div>
                        <span
                            className={`text-xs px-2 py-1 rounded ${
                                source === "db" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-amber-50 text-amber-700 border border-amber-200"
                            }`}
                            title={source === "db" ? "Fetched from curated DB" : "AI path (no curated triad found yet)"}
                        >
              {source === "db" ? "DB profile" : "AI path"}
            </span>
                    </div>

                    {!!blurb && (
                        <div className="px-6 py-4 bg-emerald-50 text-emerald-900">
                            <div className="font-semibold mb-1">Analysis</div>
                            <div className="text-sm leading-relaxed">{blurb}</div>
                        </div>
                    )}

                    {/* Potential indications */}
                    <div className="px-6 py-5">
                        <div className="font-semibold mb-3">Potential indications</div>

                        {(["Physical", "Psychological/Emotional", "Functional"] as const).map((g) => (
                            <div key={g} className="mb-5 rounded-xl border bg-sky-50/40">
                                <div className="px-4 py-2 border-b text-sm font-medium text-sky-900">{g}</div>
                                <div className="px-4 py-3">
                                    {(grouped[g] || []).length === 0 ? (
                                        <div className="text-sm text-gray-500">No items.</div>
                                    ) : (
                                        grouped[g].map((q) => {
                                            const checked = selected.includes(q.id);
                                            return (
                                                <label key={q.id} className="flex items-start gap-3 py-2">
                                                    <input
                                                        type="checkbox"
                                                        className="mt-1 h-4 w-4"
                                                        checked={checked}
                                                        onChange={() =>
                                                            setSelected((cur) => (checked ? cur.filter((x) => x !== q.id) : [...cur, q.id]))
                                                        }
                                                    />
                                                    <span className="text-sm">{q.text}</span>
                                                </label>
                                            );
                                        })
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Recommendations (from DB triad if present) */}
                    {!!reco && (
                        <div className="px-6 pb-5">
                            <div className="font-semibold mb-2">Recommendations for Rebalancing</div>
                            <pre className="whitespace-pre-wrap text-sm bg-slate-50 border rounded-lg p-3">{reco}</pre>
                        </div>
                    )}

                    {/* Stage 3 – Practitioner notes */}
                    <div className="px-6 pb-6">
                        <div className="font-semibold mb-2">Practitioner Notes (RAH-3):</div>
                        <textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={4}
                            placeholder="Enter brief clinical notes…"
                            className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"
                        />
                        <div className="mt-4">
                            <button
                                onClick={onAnalyze}
                                disabled={busy}
                                className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50"
                                title="Run AI Analysis"
                            >
                                🧠 RAI Analyze
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Stage 4 & 5 – Results */}
            {!!resultMd && (
                <div id="results" className="mt-6 bg-white border rounded-2xl overflow-hidden">
                    <div className="px-6 py-5 border-b flex items-center justify-between">
                        <div>
                            <div className="text-lg font-semibold">RAI Analysis</div>
                            <div className="text-sm text-gray-500">Case <code>{caseId}</code></div>
                        </div>
                        <div className="flex gap-2">
                            <button
                                className="text-sm px-3 py-1.5 border rounded hover:bg-gray-50"
                                onClick={() => downloadText("rai-analysis.md", resultMd)}
                            >
                                ⬇️ Download .md
                            </button>
                            <button
                                className="text-sm px-3 py-1.5 border rounded hover:bg-gray-50"
                                onClick={() => copyText(resultMd)}
                            >
                                📋 Copy
                            </button>
                        </div>
                    </div>
                    <div className="prose px-6 py-6 max-w-none">
                        <Markdown md={resultMd} />
                    </div>
                </div>
            )}
        </div>
    );
}

function RahInput(props: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div className="flex items-center gap-3">
            <div className="text-sm text-gray-600 w-36">{props.label}</div>
            <input
                value={props.value}
                onChange={(e) => props.onChange(e.target.value)}
                className="w-40 rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"
                placeholder="00.00"
            />
            <span className="text-gray-400">✎</span>
        </div>
    );
}

/** Tiny markdown renderer (headings + bullets + paragraphs) */
function Markdown({ md }: { md: string }) {
    return (
        <div className="space-y-4">
            {md.split("\n").map((line, i) => {
                if (line.startsWith("# ")) return <h1 key={i}>{line.slice(2)}</h1>;
                if (line.startsWith("## ")) return <h2 key={i}>{line.slice(3)}</h2>;
                if (line.startsWith("- ")) return <li key={i}>{line.slice(2)}</li>;
                if (line.trim() === "") return <div key={i} className="h-2" />;
                return <p key={i}>{line}</p>;
            })}
        </div>
    );
}

function copyText(text: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
}

function downloadText(filename: string, text: string) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}
