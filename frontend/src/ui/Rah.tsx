import { useEffect, useMemo, useState } from "react";
import RahDescriptionDrawer from "./RahDescriptionDrawer";

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

type RahPageResp = {
    items: RahRow[];
    total: number;
    page: number;
    page_size: number;
};

type RahDetail = {
    rah_id: number;
    details?: string;
    category?: string;
    description?: string | null;
};

export default function RahPage() {
    const [rows, setRows] = useState<RahRow[]>([]);
    const [page, setPage] = useState<number>(1);
    const [pageSize, setPageSize] = useState<number>(25);
    const [total, setTotal] = useState<number>(0);
    const [loading, setLoading] = useState<boolean>(false);

    // Drawer state (uses the "item" prop pattern)
    const [drawerItem, setDrawerItem] = useState<RahDetail | null>(null);

    async function load(p = page, ps = pageSize) {
        setLoading(true);
        try {
            const r = await fetch(
                `${API}/rah?page=${encodeURIComponent(p)}&page_size=${encodeURIComponent(ps)}`,
                { headers: { ...authHeaders() } }
            );
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const j: RahPageResp = await r.json();
            setRows(Array.isArray(j.items) ? j.items : []);
            setTotal(Number(j.total ?? 0));
            setPage(Number(j.page ?? p));
            setPageSize(Number(j.page_size ?? ps));
        } finally {
            setLoading(false);
        }
    }

    // initial load
    useEffect(() => {
        load(1, pageSize);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // when page changes, (re)load
    useEffect(() => {
        load(page, pageSize);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [page]);

    // reset to page 1 if pageSize changes
    useEffect(() => {
        setPage(1);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pageSize]);

    const pages = useMemo(
        () => Math.max(1, Math.ceil((total || 0) / (pageSize || 1))),
        [total, pageSize]
    );
    const canPrev = page > 1;
    const canNext = page < pages;

    async function openDrawer(rahId: number) {
        // fetch the full record (with description) before opening
        try {
            const r = await fetch(`${API}/rah/${rahId}`, { headers: { ...authHeaders() } });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const j: RahDetail = await r.json();
            setDrawerItem(j);
        } catch (e) {
            console.error(e);
            // open anyway with a minimal item so drawer can show a friendly message
            const fallback = rows.find((x) => x.rah_id === rahId);
            setDrawerItem({
                rah_id: rahId,
                details: fallback?.details,
                category: fallback?.category,
                description: null,
            });
        }
    }

    function closeDrawer(changed?: boolean) {
        setDrawerItem(null);
        if (changed) {
            // if description was regenerated/edited inside drawer (future),
            // reload current page to refresh the "Yes/No" badge
            load(page, pageSize);
        }
    }

    return (
        <div className="max-w-5xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">RAH IDs</h2>
                <div className="flex items-center gap-3 text-sm">
                    <span className="text-gray-500">Total: {total}</span>
                    <select
                        className="border rounded px-2 py-1"
                        value={pageSize}
                        onChange={(e) => setPageSize(parseInt(e.target.value, 10))}
                    >
                        {[10, 25, 50, 100].map((n) => (
                            <option key={n} value={n}>
                                {n} / page
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="border rounded-lg overflow-hidden bg-white">
                <div className="grid grid-cols-[110px_1fr_220px_170px] bg-gray-50 px-4 py-2 text-sm font-medium">
                    <div>RAH ID</div>
                    <div>Details</div>
                    <div>Category</div>
                    <div>Description</div>
                </div>

                {loading ? (
                    <div className="p-6 text-sm text-gray-500">Loading…</div>
                ) : rows.length === 0 ? (
                    <div className="p-6 text-sm text-gray-500">No items.</div>
                ) : (
                    rows.map((r) => (
                        <div
                            key={r.rah_id}
                            className="grid grid-cols-[110px_1fr_220px_170px] px-4 py-3 border-t text-sm"
                        >
                            <div className="tabular-nums">{r.rah_id.toFixed(2)}</div>
                            <div className="truncate">
                                {r.details || <span className="text-gray-400">—</span>}
                            </div>
                            <div className="truncate">
                                {r.category || <span className="text-gray-400">—</span>}
                            </div>
                            <div className="flex items-center gap-2">
                <span
                    className={
                        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium " +
                        (r.has_description
                            ? "bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20"
                            : "bg-yellow-50 text-yellow-700 ring-1 ring-inset ring-yellow-600/20")
                    }
                >
                  {r.has_description ? "Yes" : "No"}
                </span>

                                <button
                                    className={
                                        "ml-1 px-2 py-1 text-xs rounded border " +
                                        (r.has_description
                                            ? "hover:bg-gray-50"
                                            : "opacity-60 cursor-not-allowed")
                                    }
                                    onClick={() => r.has_description && openDrawer(r.rah_id)}
                                    disabled={!r.has_description}
                                    title={r.has_description ? "View description" : "No description available"}
                                >
                                    View
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-4">
                <button
                    className="px-3 py-2 rounded border disabled:opacity-50"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={!canPrev}
                >
                    Prev
                </button>

                <div className="text-sm text-gray-600">
                    Page <span className="font-medium">{page}</span> / {pages}
                </div>

                <button
                    className="px-3 py-2 rounded border disabled:opacity-50"
                    onClick={() => setPage((p) => Math.min(pages, p + 1))}
                    disabled={!canNext}
                >
                    Next
                </button>
            </div>

            {/* Drawer (expects { item, onClose }) */}
            <RahDescriptionDrawer item={drawerItem} onClose={() => closeDrawer(false)} />
        </div>
    );
}
