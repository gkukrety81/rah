import React from "react";
import { NavLink, useNavigate } from "react-router-dom";

export default function AppShell({ children }: { children: React.ReactNode }) {
    const navigate = useNavigate();
    const token = localStorage.getItem("token");

    function logout() {
        localStorage.removeItem("token");
        navigate("/login", { replace: true });
    }

    const linkBase =
        "px-3 py-2 rounded-md text-sm font-medium transition";
    const linkActive =
        "bg-indigo-600 text-white shadow";
    const linkIdle =
        "text-slate-700 hover:bg-slate-100";

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900">
            {/* Top Bar */}
            <header className="border-b bg-white">
                <div className="mx-auto max-w-6xl flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-indigo-600 text-white grid place-items-center font-semibold">
                            R
                        </div>
                        <div className="text-lg font-semibold">RAH Manager</div>
                    </div>

                    <nav className="flex items-center gap-2">
                        {/* 'end' makes "/" active only on exact match */}
                        <NavLink
                            to="/"
                            end
                            className={({ isActive }) =>
                                `${linkBase} ${isActive ? linkActive : linkIdle}`
                            }
                        >
                            Home
                        </NavLink>
                        <NavLink
                            to="/rah"
                            className={({ isActive }) =>
                                `${linkBase} ${isActive ? linkActive : linkIdle}`
                            }
                        >
                            RAH
                        </NavLink>
                        <NavLink
                            to="/users"
                            className={({ isActive }) =>
                                `${linkBase} ${isActive ? linkActive : linkIdle}`
                            }
                        >
                            User Management
                        </NavLink>
                    </nav>

                    <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-slate-200 grid place-items-center text-slate-600 text-xs">
                            {token ? "U" : "—"}
                        </div>
                        <button
                            onClick={logout}
                            className="px-3 py-2 rounded-md text-sm bg-slate-100 hover:bg-slate-200"
                        >
                            Logout
                        </button>
                    </div>
                </div>
            </header>

            {/* Page content */}
            <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </div>
    );
}
