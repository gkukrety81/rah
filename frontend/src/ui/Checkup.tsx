import React, { useMemo, useState } from "react";
import { ClipboardList, Eraser, Loader2, Pencil, Stethoscope, Wand2 } from "lucide-react";
import { apiCheckup, apiAnalyzeFallback } from "../api";

type Suggestion = {
    group: "Physical" | "Psychological/Emotional" | "Functional";
    text: string;
};

type CheckupResult = {
    comboTitle: string;
    analysis: string;
    suggestions: Suggestion[];
    recommendations: string;
    aiReport?: {
        correlatedSystems: string[];
        indications: string[];
        note: string;
        diagnosticSummary: string;
        recommendations: string[];
    };
};

const defaultSuggestions: Suggestion[] = [
    { group: "Physical", text: "Fatigue, weakness, or delayed healing due to impaired cellular or tissue repair." },
    { group: "Physical", text: "Increased susceptibility to infections or slow recovery, suggesting immune dysregulation." },
    { group: "Physical", text: "Dizziness / vertigo indicating vestibular (equilibrium/acoustic) involvement." },
    { group: "Physical", text: "Generalized inflammation or pain possibly from immune activation or tissue breakdown." },
    { group: "Psychological/Emotional", text: "Anxiety or low mood from chronic symptoms or uncertainty about stability (e.g., dizziness)." },
    { group: "Psychological/Emotional", text: "Frustration or cognitive fatigue due to persistent balance issues / recurrent infections." },
    { group: "Functional", text: "Reduced exercise tolerance due to unsteadiness or persistent illness." },
    { group: "Functional", text: "Concentration or memory lapses from poor sensory input or immune-related fatigue." },
];

function Field({
                   label,
                   value,
                   onChange,
                   placeholder = "00.00",
               }: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
}) {
    return (
        <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500">{label}</span>
            <input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
                className="w-28 rounded-xl border border-slate-300 bg-white/70 px-3 py-2 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
            />
            <Pencil className="h-4 w-4 text-slate-400" />
        </div>
    );
}

export default function Checkup() {
    const [id1, setId1] = useState("");
    const [id2, setId2] = useState("");
    const [id3, setId3] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<CheckupResult | null>(null);
    const [notes, setNotes] = useState("");
    const [ticks, setTicks] = useState<Record<string, boolean>>({});

    const ids = useMemo(() => {
        const nums = [id1, id2, id3]
            .map((x) => x.trim())
            .filter(Boolean)
            .map((x) => Number(x));
        return nums.filter((n) => !Number.isNaN(n));
    }, [id1, id2, id3]);

    function toggle(t: string) {
        setTicks((prev) => ({ ...prev, [t]: !prev[t] }));
    }

    async function runCheck() {
        if (ids.length === 0) return;
        setBusy(true);
        setResult(null);

        try {
            // Try the dedicated backend first; if 404/Not implemented, fall back to /ai/analyze synthesis.
            const r = await apiCheckup(ids);
            setResult(r);
            // hydrate default tick boxes if backend supplied suggestions
            const initial: Record<string, boolean> = {};
            (r.suggestions?.map((s) => s.text) ?? defaultSuggestions.map((s) => s.text)).forEach((t) => (initial[t] = false));
            setTicks(initial);
        } catch (e: any) {
            const fallback = await apiAnalyzeFallback(ids);
            setResult(fallback);
            const initial: Record<string, boolean> = {};
            (fallback.suggestions ?? defaultSuggestions).forEach((s: any) => (initial[s.text ?? s] = false));
            setTicks(initial);
        } finally {
            setBusy(false);
        }
    }

    function resetAll() {
        setId1("");
        setId2("");
        setId3("");
        setResult(null);
        setTicks({});
        setNotes("");
    }

    const chosen = Object.entries(ticks)
        .filter(([, v]) => v)
        .map(([k]) => k);

    return (
        <div className="mx-auto max-w-5xl space-y-6">
            {/* Header card */}
            <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
                    <Stethoscope className="h-5 w-5 text-indigo-600" />
                    <h2 className="text-lg font-semibold text-slate-800">RAH check-up</h2>
                </div>

                <div className="flex flex-wrap items-center gap-4 bg-indigo-50/60 px-5 py-4">
                    <Field label="RAH check-up 1" value={id1} onChange={setId1} />
                    <Field label="RAH check-up 2" value={id2} onChange={setId2} />
                    <Field label="RAH check-up 3" value={id3} onChange={setId3} />
                    <div className="ml-auto flex items-center gap-3">
                        <button
                            onClick={runCheck}
                            disabled={busy || ids.length === 0}
                            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                            Check
                        </button>
                        <button
                            onClick={resetAll}
                            className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-100"
                        >
                            <Eraser className="h-4 w-4" />
                            Reset
                        </button>
                    </div>
                </div>
            </div>

            {/* When we have a result */}
            {result && (
                <>
                    {/* Combo title */}
                    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="px-6 py-4">
                            <div className="text-base">
                                <span className="font-semibold text-slate-800">Combination: </span>
                                <span className="text-slate-700">{result.comboTitle}</span>
                            </div>
                        </div>
                        <div className="border-t border-slate-100 bg-emerald-50/70 px-6 py-4 text-emerald-900">
                            <div className="font-semibold">Analysis</div>
                            <p className="mt-1 text-sm leading-relaxed">{result.analysis}</p>
                        </div>

                        {/* Potential indications */}
                        <div className="border-t border-slate-100 bg-sky-50/70 px-6 py-5">
                            <div className="mb-2 font-semibold text-slate-800">Potential Indications</div>
                            <div className="grid gap-4 md:grid-cols-3">
                                {((result.suggestions?.length ? result.suggestions : defaultSuggestions) as Suggestion[]).map((s, idx) => (
                                    <label
                                        key={idx}
                                        className="group flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition hover:border-indigo-300"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={!!ticks[s.text]}
                                            onChange={() => toggle(s.text)}
                                            className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                        />
                                        <div>
                                            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{s.group}</div>
                                            <div className="text-sm text-slate-700">{s.text}</div>
                                        </div>
                                    </label>
                                ))}
                            </div>
                        </div>

                        {/* Recommendations */}
                        <div className="border-t border-slate-100 bg-violet-50/70 px-6 py-4">
                            <div className="font-semibold text-slate-800">Recommendations for Rebalancing</div>
                            <p className="mt-1 text-sm leading-relaxed text-slate-700">{result.recommendations}</p>
                        </div>
                    </div>

                    {/* Practitioner notes */}
                    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="flex items-center gap-2 border-b border-slate-100 px-6 py-3">
                            <ClipboardList className="h-4 w-4 text-slate-500" />
                            <div className="font-medium text-slate-800">Practitioner Notes (RAH-3):</div>
                        </div>
                        <div className="px-6 py-4">
              <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={4}
                  placeholder="The client is in good health …"
                  className="w-full rounded-xl border border-slate-300 bg-white/70 px-3 py-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
              />
                            <div className="mt-3">
                                <button
                                    onClick={async () => {
                                        setBusy(true);
                                        try {
                                            const r = await apiCheckup(ids, chosen, notes);
                                            setResult(r);
                                        } finally {
                                            setBusy(false);
                                        }
                                    }}
                                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700"
                                >
                                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Stethoscope className="h-4 w-4" />}
                                    RAI Analyze
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* AI Analysis (stage 4/5) */}
                    {result.aiReport && (
                        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                            <div className="border-b border-slate-100 px-6 py-3">
                                <div className="font-semibold text-slate-800">RAI Analysis</div>
                            </div>
                            <div className="space-y-6 px-6 py-5 text-slate-800">
                                <section>
                                    <h3 className="text-lg font-semibold">Correlated Systems Analysis</h3>
                                    <ul className="mt-2 list-disc pl-5 text-sm">
                                        {result.aiReport.correlatedSystems.map((x, i) => (
                                            <li key={i}>{x}</li>
                                        ))}
                                    </ul>
                                </section>
                                <section>
                                    <h3 className="text-lg font-semibold">Indication Interpretation</h3>
                                    <ul className="mt-2 list-disc pl-5 text-sm">
                                        {result.aiReport.indications.map((x, i) => (
                                            <li key={i}>{x}</li>
                                        ))}
                                    </ul>
                                </section>
                                <section>
                                    <h3 className="text-lg font-semibold">Note Synthesis</h3>
                                    <p className="mt-1 text-sm">{result.aiReport.note}</p>
                                </section>
                                <section>
                                    <h3 className="text-lg font-semibold">~200-Word Diagnostic Summary</h3>
                                    <p className="mt-1 text-sm leading-relaxed">{result.aiReport.diagnosticSummary}</p>
                                </section>
                                <section>
                                    <h3 className="text-lg font-semibold">Tailored Recommendations</h3>
                                    <ul className="mt-2 list-disc pl-5 text-sm">
                                        {result.aiReport.recommendations.map((x, i) => (
                                            <li key={i}>{x}</li>
                                        ))}
                                    </ul>
                                </section>
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
