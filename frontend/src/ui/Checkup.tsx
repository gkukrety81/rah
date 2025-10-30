// frontend/src/ui/Checkup.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import {
    startCheckup,
    saveCheckupAnswers,
    analyzeCheckup,
    listCases,
    translateMarkdown,
} from "../api";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";

type Group = "Physical" | "Psychological/Emotional" | "Functional";
type Question = { id: string; text: string; group: Group };

type HistoryItem = {
    case_id: string;
    rah_ids: number[];
    combination: string | null;
    analysis_blurb: string | null;
    recommendations: string | null;
    created_at: string;
    source: "db" | "ai" | string;
};

export default function Checkup() {
    const [rah1, setRah1] = useState("00.00");
    const [rah2, setRah2] = useState("00.00");
    const [rah3, setRah3] = useState("00.00");

    const [busy, setBusy] = useState(false);
    const [caseId, setCaseId] = useState<string | null>(null);

    const [combo, setCombo] = useState("");
    const [blurb, setBlurb] = useState("");
    const [reco, setReco] = useState<string>(""); // NEW: recommendations panel
    const [source, setSource] = useState<"db" | "ai" | "">("");

    const [qs, setQs] = useState<Question[]>([]);
    const [selected, setSelected] = useState<string[]>([]);
    const [notes, setNotes] = useState("");

    const [resultMd, setResultMd] = useState("");
    const [translatedMd, setTranslatedMd] = useState<string>("");

    // History drawer
    const [histOpen, setHistOpen] = useState(false);
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const resultsRef = useRef<HTMLDivElement | null>(null);

    function resetAll() {
        setRah1("00.00"); setRah2("00.00"); setRah3("00.00");
        setBusy(false); setCaseId(null);
        setCombo(""); setBlurb(""); setReco(""); setSource("");
        setQs([]); setSelected([]); setNotes("");
        setResultMd(""); setTranslatedMd("");
    }

    async function onCheck() {
        setBusy(true);
        try {
            const ids = [parseFloat(rah1), parseFloat(rah2), parseFloat(rah3)];
            const res = await startCheckup(ids);
            setCaseId(res.case_id);
            setCombo(res.combination_title || "");
            setBlurb(res.analysis_blurb || "");
            setQs((res.questions || []) as Question[]);
            setSelected([]);
            setResultMd("");
            setTranslatedMd("");
            setReco(res.recommendations || "");
            setSource(res.source || "");
            window.scrollTo({ top: 0, behavior: "smooth" });
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
            const res = await analyzeCheckup(caseId);
            setResultMd(res.markdown || "");
            setTranslatedMd("");
            setTimeout(() => {
                document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
            }, 40);
        } catch (e) {
            console.error(e);
            alert("AI analysis failed");
        } finally {
            setBusy(false);
        }
    }

    // Group qs
    const grouped = useMemo(() => {
        const g: Record<Group, Question[]> = {
            Physical: [], "Psychological/Emotional": [], Functional: []
        };
        for (const q of qs) (g[q.group] || g.Physical).push(q);
        return g;
    }, [qs]);

    // History
    async function openHistory() {
        try {
            const data = await listCases(25);
            setHistory(data.items || []);
            setHistOpen(true);
        } catch (e) {
            console.error(e);
            alert("Could not load history");
        }
    }
    function loadHistoryItem(it: HistoryItem) {
        setRah1((it.rah_ids[0] ?? 0).toFixed(2));
        setRah2((it.rah_ids[1] ?? 0).toFixed(2));
        setRah3((it.rah_ids[2] ?? 0).toFixed(2));
        setCaseId(it.case_id);
        setCombo(it.combination || "");
        setBlurb(it.analysis_blurb || "");
        setReco(it.recommendations || "");
        setSource((it.source as any) || "");
        setQs([]); setSelected([]); setNotes("");
        setResultMd(""); setTranslatedMd("");
        setHistOpen(false);
    }

    // Translate Stage-5 (markdown) to German
    async function onTranslateDE() {
        try {
            const text = resultMd || (buildStage2Markdown(combo, blurb, reco));
            if (!text.trim()) return;
            const res = await translateMarkdown(text, "de");
            setTranslatedMd(res.text || "");
            setTimeout(() => {
                document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
            }, 40);
        } catch (e) {
            console.error(e);
            alert("Translate failed");
        }
    }

    // PDF export from the results panel
    async function onExportPDF() {
        const node = resultsRef.current;
        if (!node) return;
        const canvas = await html2canvas(node, { scale: 2 });
        const img = canvas.toDataURL("image/png");
        const pdf = new jsPDF({ unit: "pt", format: "a4" });
        const pageWidth = pdf.internal.pageSize.getWidth();
        const ratio = pageWidth / canvas.width;
        const imgHeight = canvas.height * ratio;
        pdf.addImage(img, "PNG", 0, 0, pageWidth, imgHeight);
        pdf.save(`RAI_${caseId ?? "report"}.pdf`);
    }

    const displayMd = translatedMd || resultMd;

    return (
        <div className="max-w-5xl mx-auto">
            {/* Header */}
            <div className="bg-white rounded-2xl shadow-sm border">
                <div className="px-6 py-5 border-b flex items-center justify-between">
                    <div>
                        <div className="font-semibold text-lg">RAH check-up</div>
                        <div className="text-gray-500 text-sm">Enter three RAH IDs and click <b>Check</b>.</div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={openHistory}
                                className="rounded-md border px-3 py-2 hover:bg-gray-50">🗂 Case history</button>
                        <button onClick={onCheck} disabled={busy}
                                className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50">
                            ✨ Check
                        </button>
                        <button onClick={resetAll} disabled={busy}
                                className="rounded-md border px-4 py-2 hover:bg-gray-50 disabled:opacity-50">
                            🧹 Reset
                        </button>
                    </div>
                </div>
                <div className="px-6 py-5 bg-slate-50/60">
                    <div className="flex flex-wrap items-center gap-6">
                        <RahInput label="RAH check-up 1" value={rah1} onChange={setRah1}/>
                        <RahInput label="RAH check-up 2" value={rah2} onChange={setRah2}/>
                        <RahInput label="RAH check-up 3" value={rah3} onChange={setRah3}/>
                    </div>
                </div>
            </div>

            {/* Stage 2 – Combination + Analysis + (DB badge) + Recommendations */}
            {caseId && (
                <div className="mt-6 bg-white rounded-2xl border overflow-hidden">
                    <div className="px-6 py-5 border-b flex items-center justify-between">
                        <div>
                            <div className="text-sm text-gray-500 uppercase tracking-wide">Combination</div>
                            <div className="text-base font-medium mt-1">{combo || "—"}</div>
                        </div>
                        {source && (
                            <span className={`text-xs px-2 py-1 rounded border ${source === "db" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-sky-50 text-sky-700 border-sky-200"}`}>
                {source === "db" ? "From Database" : "From AI"}
              </span>
                        )}
                    </div>

                    {blurb && (
                        <div className="px-6 py-4 bg-emerald-50 text-emerald-900">
                            <div className="font-semibold mb-1">Analysis</div>
                            <div className="text-sm leading-relaxed">{blurb}</div>
                        </div>
                    )}

                    {reco && (
                        <div className="px-6 py-4 bg-fuchsia-50 text-fuchsia-900">
                            <div className="flex items-center justify-between">
                                <div className="font-semibold mb-1">Recommendations for Rebalancing</div>
                            </div>
                            <div className="text-sm whitespace-pre-line">{reco}</div>
                        </div>
                    )}

                    {/* Potential indications */}
                    <div className="px-6 py-5">
                        <div className="font-semibold mb-3">Potential indications</div>
                        {(["Physical","Psychological/Emotional","Functional"] as const).map((g) => (
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
                                                    <input type="checkbox" className="mt-1 h-4 w-4" checked={checked}
                                                           onChange={() => setSelected((cur) =>
                                                               checked ? cur.filter((x) => x !== q.id) : [...cur, q.id])}/>
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
                        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4}
                                  placeholder="Enter brief clinical notes…"
                                  className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"/>
                        <div className="mt-4 flex gap-2">
                            <button onClick={onAnalyze} disabled={busy}
                                    className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50">
                                🧠 RAI Analyze
                            </button>
                            {!!displayMd && (
                                <>
                                    <button onClick={onTranslateDE}
                                            className="rounded-md border px-3 py-2 hover:bg-gray-50">
                                        🌐 Translate → German
                                    </button>
                                    <button onClick={onExportPDF}
                                            className="rounded-md border px-3 py-2 hover:bg-gray-50">
                                        ⤓ Export PDF
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Stage 4/5 – Results (original or translated) */}
            {!!displayMd && (
                <div id="results" ref={resultsRef} className="mt-6 bg-white border rounded-2xl overflow-hidden">
                    <div className="px-6 py-5 border-b">
                        <div className="text-lg font-semibold">RAI Analysis</div>
                        <div className="text-sm text-gray-500">
                            Results for case <code>{caseId}</code>{translatedMd ? " (German)" : ""}
                        </div>
                    </div>
                    <div className="prose px-6 py-6 max-w-none">
                        <Markdown md={displayMd}/>
                    </div>
                </div>
            )}

            {/* History drawer */}
            {histOpen && (
                <div className="fixed inset-0 bg-black/30 flex justify-end z-50" onClick={()=>setHistOpen(false)}>
                    <div className="w-[420px] h-full bg-white shadow-xl p-4 overflow-y-auto" onClick={(e)=>e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-3">
                            <div className="font-semibold">Case History</div>
                            <button onClick={()=>setHistOpen(false)} className="text-sm">✕ Close</button>
                        </div>
                        {history.length === 0 ? (
                            <div className="text-sm text-gray-500">No cases yet.</div>
                        ) : (
                            <ul className="space-y-2">
                                {history.map((it)=>(
                                    <li key={it.case_id}>
                                        <button
                                            onClick={()=>loadHistoryItem(it)}
                                            className="w-full text-left rounded-lg border p-3 hover:bg-gray-50"
                                        >
                                            <div className="text-sm font-medium">{(it.combination || "—").slice(0,120)}</div>
                                            <div className="text-xs text-gray-500 mt-1">
                                                {it.rah_ids.map(v=>v.toFixed(2)).join(", ")} • {new Date(it.created_at).toLocaleString()} • {it.source}
                                            </div>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function RahInput(props: {label:string; value:string; onChange:(v:string)=>void}) {
    return (
        <div className="flex items-center gap-3">
            <div className="text-sm text-gray-600 w-36">{props.label}</div>
            <input value={props.value} onChange={(e)=>props.onChange(e.target.value)}
                   className="w-40 rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-500"
                   placeholder="00.00"/>
            <span className="text-gray-400">✎</span>
        </div>
    );
}

function Markdown({ md }: { md: string }) {
    return (
        <div className="space-y-4">
            {md.split("\n").map((line, i) => {
                if (line.startsWith("# ")) return <h1 key={i}>{line.slice(2)}</h1>;
                if (line.startsWith("## ")) return <h2 key={i}>{line.slice(3)}</h2>;
                if (line.startsWith("- ")) return <li key={i}>{line.slice(2)}</li>;
                if (line.trim() === "") return <div key={i} className="h-2"/>;
                return <p key={i}>{line}</p>;
            })}
        </div>
    );
}

// Build Stage-2 markdown (when Stage-5 isn’t yet run)
function buildStage2Markdown(combo: string, blurb: string, reco: string) {
    const parts: string[] = [];
    parts.push(`# Combination\n${combo || "—"}`);
    if (blurb) parts.push(`\n## Analysis\n${blurb}`);
    if (reco)  parts.push(`\n## Recommendations for Rebalancing\n${reco}`);
    return parts.join("\n");
}
