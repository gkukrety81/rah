import { NavLink, useNavigate } from "react-router-dom";
import { Outlet } from "react-router-dom";

export default function AppShell() {
    const navigate = useNavigate();
    const logout = () => {
        localStorage.removeItem("token");
        navigate("/login", { replace: true });
    };

    const link = ({ isActive }: { isActive: boolean }) =>
        `px-3 py-2 rounded-md text-sm ${isActive ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-100"}`;

    return (
        <div className="min-h-screen flex flex-col">
            <header className="border-b bg-white">
                <div className="mx-auto w-full max-w-6xl flex items-center justify-between px-4 h-14">
                    <div className="flex items-center gap-6">
                        <div className="font-semibold">RAH Manager</div>
                        <nav className="flex items-center gap-2">
                            <NavLink to="/" end className={link}>Home</NavLink>
                            <NavLink to="/rah" className={link}>RAH</NavLink>
                            <NavLink to="/checkup" className={link}>Check-up</NavLink>
                            <NavLink to="/users" className={link}>User Management</NavLink>
                        </nav>
                    </div>
                    <button onClick={logout} className="px-3 py-1.5 border rounded-md text-sm">Logout</button>
                </div>
            </header>

            {/* IMPORTANT: this renders the current route */}
            <main className="flex-1 bg-gray-50">
                <div className="mx-auto w-full max-w-6xl px-4 py-6">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
