import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom";
import AppShell from "./layout/AppShell";
import Login from "./Login";
import Landing from "./Landing";      // Home
import RahPage from "./Rah";          // RAH table page
import Checkup from "./Checkup";      // Check-up flow
import Users from "./Users";          // User management

function isAuthed() {
    return !!localStorage.getItem("token");
}

function Guard() {
    return isAuthed() ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Public */}
                <Route path="/login" element={<Login />} />

                {/* Protected */}
                <Route element={<Guard />}>
                    <Route element={<AppShell />}>
                        <Route index element={<Landing />} />
                        <Route path="/" element={<Landing />} />
                        <Route path="/rah" element={<RahPage />} />
                        <Route path="/checkup" element={<Checkup />} />
                        <Route path="/users" element={<Users />} />
                    </Route>
                </Route>

                {/* Fallback */}
                <Route path="*" element={<Navigate to={isAuthed() ? "/" : "/login"} replace />} />
            </Routes>
        </BrowserRouter>
    );
}
