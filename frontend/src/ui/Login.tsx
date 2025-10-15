import React, { useState } from 'react'
import { authLogin, setToken } from "../api";
const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function Login({ onLogin }: { onLogin: () => void }){
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit(e: React.FormEvent){
    e.preventDefault()
    setBusy(true); setErr(null)
    try{
      const r = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ username, password })
      })
      if(!r.ok){
        const t = await r.text()
        setErr(t || 'Invalid credentials')
        return
      }
      const j = await r.json()
      localStorage.setItem('token', j.access_token)
      onLogin()
    } finally {
      setBusy(false)
    }
  }

    const onSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setErr(null);
        try {
            const data = await authLogin(username, password);
            setToken(data.access_token);              // 👈 store JWT
            // navigate to / (or /home) after login
            window.location.href = "/";
        } catch (e: any) {
            setErr(e.message ?? String(e));
        }
    };

  return (
    <div style={{display:'grid', placeItems:'center', height:'100vh', fontFamily:'sans-serif'}}>
      <form onSubmit={submit} style={{minWidth:320, padding:24, border:'1px solid #ddd', borderRadius:12}}>
        <h2>Sign in</h2>
        <div style={{margin:'8px 0'}}>
          <div>Username</div>
          <input value={username} onChange={e=>setUsername(e.target.value)} />
        </div>
        <div style={{margin:'8px 0'}}>
          <div>Password</div>
          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} />
        </div>
        {err && <div style={{color:'crimson', marginTop:8}}>{err}</div>}
        <button disabled={busy} style={{marginTop:12, width:'100%'}}>{busy?'Signing in...':'Sign in'}</button>
      </form>
    </div>
  )
}
