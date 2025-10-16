import React, { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

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

type RahPayload =
    | RahRow[]
    | {
    items: RahRow[];
    total?: number;
    limit?: number;
    offset?: number;
};

export default function RahPage() {
    const [rows, setRows] = useState<RahRow[]>([]);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState<number | null>(null);
    const limit = 25;

    async function load(p = page) {
        const offset = (p - 1) * limit;
        const res = await fetch(`${API}/rah?limit=${limit}&offset=${offset}`, {
            headers: { ...authHeaders() },
        });

        if (!res.ok) {
            console.error("RAH fetch failed", await res.text());
            setRows([]);
            return;
        }

        const data: RahPayload = await res.json();

        const items = Array.isArray(data) ? data : data.items ?? [];
        setRows(items);

        // If backend provides a total, use it for better paging.
        if (!Array.isArray(data) && typeof data.total === "number") {
            setTotal(data.total);
        } else {
            // Fallback: unknown total; set to a rolling minimum to keep pager sane.
            const atLeast = offset + items.length;
            setTotal((prev) => (prev === null ? atLeast : Math.max(prev, atLeast)));
        }
    }

    useEffect(() => {
        load(1);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        load(page);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [page]);

    const canPrev = page > 1;
    // If we know total, compute final page; if not, allow Next until an empty page shows up.
    const knownTotal = total !== null;
    const lastPage = knownTotal ? Math.max(1, Math.ceil((total as number) / limit)) : undefined;
    const canNext = knownTotal ? page < (lastPage as number) : rows.length === limit;

    return (
        <div className="space-y-4">
            <h2 className="text-xl font-semibold">RAH IDs</h2>

            <div className="overflow-x-auto rounded-lg border bg-white">
                <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600">
                    <tr>
                        <th className="px-4 py-3 text-left">RAH ID</th>
                        <th className="px-4 py-3 text-left">Details</th>
                        <th className="px-4 py-3 text-left">Category</th>
                        <th className="px-4 py-3 text-left">Description</th>
                    </tr>
                    </thead>
                    <tbody>
                    {rows.map((r) => (
                        <tr key={r.rah_id} className="border-t">
                            <td className="px-4 py-3">{r.rah_id.toFixed(2)}</td>
                            <td className="px-4 py-3">{r.details}</td>
                            <td className="px-4 py-3">{r.category}</td>
                            <td className="px-4 py-3">
                                {r.has_description ? (
                                    <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
                      Yes
                    </span>
                                ) : (
                                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
                      No
                    </span>
                                )}
                            </td>
                        </tr>
                    ))}

                    {rows.length === 0 && (
                        <tr>
                            <td className="px-4 py-8 text-center text-slate-500" colSpan={4}>
                                No data.
                            </td>
                        </tr>
                    )}
                    </tbody>
                </table>
            </div>

            {/* Pager */}
            <div className="flex items-center gap-2">
                <button
                    className="px-3 py-2 rounded-md border bg-white disabled:opacity-50"
                    disabled={!canPrev}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                    Prev
                </button>
                <span className="text-sm text-slate-600">
          Page {page}
                    {knownTotal && lastPage ? ` / ${lastPage}` : ""}
        </span>
                <button
                    className="px-3 py-2 rounded-md border bg-white disabled:opacity-50"
                    disabled={!canNext}
                    onClick={() => setPage((p) => p + 1)}
                >
                    Next
                </button>
            </div>
        </div>
    );
}
