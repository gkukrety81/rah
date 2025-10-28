// frontend/src/ui/Checkup.tsx
import { useState } from "react";
import { startCheckup, saveCheckupAnswers, analyzeCheckup } from "../api";

type Question = { id: string; text: string; group: string };

export default function Checkup() {
    // Stage state
    const [rah1, setRah1] = useState("00.00");
    const [rah2, setRah2] = useState("00.00");
    const [rah3, setRah3] = useState("00.00");

    const [busy, setBusy] = useState(false);
    const [caseId, setCaseIdState] = useState<string | null>(
        localStorage.getItem("current_case_id")
    );
    const [combo, setCombo] = useState("");
    const [blurb, setBlurb] = useState("");
    const [qs, setQs] = useState<Question[]>([]);
    const [selected, setSelected] = useState<string[]>([]);
    const [notes, setNotes] = useState("");

    const [resultMd, setResultMd] = useState("");

    // keep case id in state + localStorage so it survives re-rendering
    function setCaseId(newId: string | null) {
        setCaseIdState(newId);
        if (newId) localStorage.setItem("current_case_id", newId);
        else localStorage.removeItem("current_case_id");
    }

    function resetAll() {
        setRah1("00.00");
        setRah2("00.00");
        setRah3("00.00");
        setBusy(false);
        setCaseId(null);
        setCombo("");
        setBlurb("");
        setQs([]);
        setSelected([]);
        setNotes("");
        setResultMd("");
    }

    async function onCheck() {
        if (busy) return;
        setBusy(true);
        try {
            const ids = [parseFloat(rah1), parseFloat(rah2), parseFloat(rah3)];
            const res = await startCheckup(ids);
            setCaseId(res.case_id);
            setCombo(res.combination_title);
            setBlurb(res.analysis_blurb);
            setQs(res.questions || []);
            setSelected([]);
            setResultMd("");
            window.scrollTo({ top: 0, behavior: "smooth" });
        } catch (e) {
            console.error(e);
            alert("Check failed");
        } finally {
            setBusy(false);
        }
    }

    async function onAnalyze() {
        if (!caseId) {
            alert("No case found — click Check first.");
            return;
        }
        setBusy(true);
        try {
            await saveCheckupAnswers(caseId, selected, notes);
            const res = await analyzeCheckup(caseId);
            setResultMd(res.markdown || "");
            setTimeout(() => {
                document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
            }, 50);
        } catch (e) {
            console.error(e);
            alert("AI analysis failed");
        } finally {
            setBusy(false);
        }
    }

    const groups = ["Physical", "Psychological/Emotional", "Functional"] as const;
    const grouped: Record<string, Question[]> = {
        Physical: [],
        "Psychological/Emotional": [],
        Functional: [],
    };
    for (const q of qs) (grouped[q.group] ?? grouped["Physical"]).push(q);

    return (
        <div className="max-w-5xl mx-auto">
            {/* Stage 1 Header */}
            <div className="bg-white rounded-2xl shadow-sm border">
                <div className="px-6 py-5 border-b flex items-center justify-between">
                    <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-violet-100 text-violet-700">
              ⚕️
            </span>
                        <div>
                            <div className="font-semibold text-lg">RAH check-up</div>
                            <div className="text-gray-500 text-sm">
                                Enter three RAH IDs and click <span className="font-medium">Check</span>.
                            </div>
                        </div>
                    </div>

                    <div className="flex gap-3 pointer-events-auto">
                        <button
                            type="button"
                            onClick={onCheck}
                            disabled={busy}
                            className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Generate questionnaire"
                        >
                            ✨ Check
                        </button>
                        <button
                            type="button"
                            onClick={resetAll}
                            disabled={busy}
                            className="inline-flex items-center gap-2 rounded-md border px-4 py-2 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Reset all"
                        >
                            🧹 Reset
                        </button>
                    </div>
                </div>

                {/* Stage 1 inputs */}
                <div className="px-6 py-5 bg-slate-50/60">
                    <div className="flex flex-wrap items-center gap-6">
                        <RahInput label="RAH check-up 1" value={rah1} onChange={setRah1} />
                        <RahInput label="RAH check-up 2" value={rah2} onChange={setRah2} />
                        <RahInput label="RAH check-up 3" value={rah3} onChange={setRah3} />
                    </div>
                </div>
            </div>

            {/* Stage 2 – Combination + Analysis + Questions */}
            {caseId && (
                <div className="mt-6 bg-white rounded-2xl border overflow-hidden">
                    <div className="px-6 py-5 border-b">
                        <div className="text-sm text-gray-500 uppercase tracking-wide">Combination</div>
                        <div className="text-base font-medium mt-1">{combo || "—"}</div>
                    </div>

                    {blurb && (
                        <div className="px-6 py-4 bg-emerald-50 text-emerald-900">
                            <div className="font-semibold mb-1">Analysis</div>
                            <div className="text-sm leading-relaxed">{blurb}</div>
                        </div>
                    )}

                    <div className="px-6 py-5">
                        <div className="font-semibold mb-3">Potential indications</div>

                        {groups.map((g) => (
                            <div key={g} className="mb-5 rounded-xl border bg-sky-50/40">
                                <div className="px-4 py-2 border-b text-sm font-medium text-sky-900">
                                    {g}
                                </div>
                                <div className="px-4 py-3">
                                    {(grouped[g] || []).length === 0 ? (
                                        <div className="text-sm text-gray-500">No items.</div>
                                    ) : (
                                        (grouped[g] || []).map((q) => {
                                            const checked = selected.includes(q.id);
                                            return (
                                                <label key={q.id} className="flex items-start gap-3 py-2">
                                                    <input
                                                        type="checkbox"
                                                        className="mt-1 h-4 w-4"
                                                        checked={checked}
                                                        onChange={() =>
                                                            setSelected((cur) =>
                                                                checked ? cur.filter((x) => x !== q.id) : [...cur, q.id]
                                                            )
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

                    {/* Stage 3 – Practitioner notes */}
                    <div className="px-6 pb-6">
                        <div className="font-semibold mb-2">Practitioner Notes (RAH-3):</div>
                        <textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={4}
                            placeholder="Enter brief clinical notes, e.g. 'Client in good health, complains of eye strain and persistent fatigue...'"
                            className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"
                        />
                        <div className="mt-4">
                            <button
                                type="button"
                                onClick={onAnalyze}
                                disabled={busy}
                                className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Run AI Analysis"
                            >
                                🧠 RAI Analyze
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Stage 4 & 5 – Results */}
            {resultMd && (
                <div id="results" className="mt-6 bg-white border rounded-2xl overflow-hidden">
                    <div className="px-6 py-5 border-b flex items-center justify-between">
                        <div>
                            <div className="text-lg font-semibold">RAI Analysis</div>
                            <div className="text-sm text-gray-500">Results for case <code>{caseId}</code></div>
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={() => window.print()}
                                className="inline-flex items-center gap-2 rounded-md border px-3 py-2 hover:bg-gray-50"
                                title="Export PDF"
                            >
                                🖨️ Export PDF
                            </button>
                            <button
                                onClick={async () => {
                                    if (!caseId) return;
                                    try {
                                        const r = await translateCheckup(caseId, "de");
                                        setResultMd(r.markdown || resultMd); // swap to German
                                    } catch (e) {
                                        console.error(e);
                                        alert("Translate failed");
                                    }
                                }}
                                className="inline-flex items-center gap-2 rounded-md border px-3 py-2 hover:bg-gray-50"
                                title="Translate to German"
                            >
                                🇩🇪 Deutsch
                            </button>
                        </div>
                    </div>
                    <div className="prose px-6 py-6 max-w-none print:prose-sm">
                        <Markdown md={resultMd} />
                    </div>
                </div>
            )}
        </div>
    );
}

function RahInput({
                      label,
                      value,
                      onChange,
                  }: {
    label: string;
    value: string;
    onChange: (s: string) => void;
}) {
    return (
        <div className="flex items-center gap-3">
            <div className="text-sm text-gray-600 w-36">{label}</div>
            <input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className="w-40 rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"
                placeholder="00.00"
            />
            <span className="text-gray-400">✎</span>
        </div>
    );
}

function Markdown({ md }: { md: string }) {
    // Tiny safe renderer for the headings/bullets we output
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
