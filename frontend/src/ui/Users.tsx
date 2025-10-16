import React, { useEffect, useState } from "react";
const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
    const t = localStorage.getItem("token");
    return t ? { Authorization: `Bearer ${t}` } : {};
}

type UserRow = {
    user_id: string;
    username: string;
    first_name?: string;
    last_name?: string;
    email?: string;
    branch?: string;
    location?: string;
    is_active: boolean;
};

export default function Users() {
    const [users, setUsers] = useState<UserRow[]>([]);

    async function load() {
        const r = await fetch(`${API}/users`, { headers: { ...authHeaders() } });
        const j = await r.json();
        setUsers(j);
    }

    useEffect(() => {
        load();
    }, []);

    return (
        <div className="space-y-4">
            <h2 className="text-xl font-semibold">User Management</h2>
            <div className="overflow-x-auto rounded-lg border bg-white">
                <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600">
                    <tr>
                        <th className="px-4 py-3 text-left">Name</th>
                        <th className="px-4 py-3 text-left">Username</th>
                        <th className="px-4 py-3 text-left">Email</th>
                        <th className="px-4 py-3 text-left">Branch</th>
                        <th className="px-4 py-3 text-left">Location</th>
                        <th className="px-4 py-3 text-left">Active</th>
                    </tr>
                    </thead>
                    <tbody>
                    {users.map((u) => (
                        <tr key={u.user_id} className="border-t">
                            <td className="px-4 py-3">
                                {(u.first_name || "") + " " + (u.last_name || "")}
                            </td>
                            <td className="px-4 py-3">{u.username}</td>
                            <td className="px-4 py-3">{u.email}</td>
                            <td className="px-4 py-3">{u.branch}</td>
                            <td className="px-4 py-3">{u.location}</td>
                            <td className="px-4 py-3">{u.is_active ? "Yes" : "No"}</td>
                        </tr>
                    ))}
                    {users.length === 0 && (
                        <tr>
                            <td className="px-4 py-8 text-center text-slate-500" colSpan={6}>
                                No users.
                            </td>
                        </tr>
                    )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
