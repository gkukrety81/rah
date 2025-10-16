// frontend/src/ui/App.tsx
import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";

import Login from "./Login";
import Landing from "./Landing";
import Users from "./Users";
import RahPage from "./Rah";
import AppShell from "./layout/AppShell";

function isAuthed() {
    return !!localStorage.getItem("token");
}

// Simple auth guard that redirects to /login if not authenticated
function Guard({ children }: { children: React.ReactNode }) {
    const loc = useLocation();
    if (!isAuthed()) {
        return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
    }
    return <>{children}</>;
}

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Public */}
                <Route path="/login" element={<Login />} />

                {/* Protected pages inside the enterprise shell */}
                <Route
                    path="/"
                    element={
                        <Guard>
                            <AppShell>
                                <Landing />
                            </AppShell>
                        </Guard>
                    }
                />
                <Route
                    path="/rah"
                    element={
                        <Guard>
                            <AppShell>
                                <RahPage />
                            </AppShell>
                        </Guard>
                    }
                />
                <Route
                    path="/users"
                    element={
                        <Guard>
                            <AppShell>
                                <Users />
                            </AppShell>
                        </Guard>
                    }
                />

                {/* Fallback */}
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}
