import React, { useEffect, useState } from 'react'
const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

function authHeaders(){
  const t = localStorage.getItem('token')
  return t ? { 'Authorization': `Bearer ${t}` } : {}
}

type RahRow = { rah_id: number, details?: string, category?: string, has_description: boolean }

function Chat(){
  const [prompt, setPrompt] = useState('Explain the semicircular canals in vestibular function.')
  const [resp, setResp] = useState('')

  async function send(){
    setResp('...')
    const r = await fetch(`${API}/ai/chat`, { method:'POST', headers:{'Content-Type':'application/json', ...authHeaders()}, body: JSON.stringify({ prompt }) })
    const j = await r.json()
    setResp(j.response || '')
  }

  return (
    <div style={{border:'1px solid #ddd', borderRadius:12, padding:12}}>
      <h3>AI Chat</h3>
      <textarea rows={5} style={{width:'100%'}} value={prompt} onChange={e=>setPrompt(e.target.value)} />
      <div style={{marginTop:8}}><button onClick={send}>Ask</button></div>
      <pre style={{whiteSpace:'pre-wrap'}}>{resp}</pre>
    </div>
  )
}

export default function Landing(){
  const [list, setList] = useState<RahRow[]>([])
  const [rahId, setRahId] = useState<string>('58.41')
  const [details, setDetails] = useState<string>('Semicircular canals')
  const [category, setCategory] = useState<string>('Acoustic organ')
  const [busy, setBusy] = useState<boolean>(false)

  async function load() {
    const r = await fetch(`${API}/rah`, { headers: { ...authHeaders() } })
    const j = await r.json()
    setList(j)
  }

  async function createRah() {
    setBusy(true)
    try {
      const r = await fetch(`${API}/rah`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ rah_id: parseFloat(rahId), details, category, auto_generate: false })
      })
      if (!r.ok) alert('Create failed')
      await load()
    } finally {
      setBusy(false)
    }
  }

  useEffect(()=>{ load() }, [])

  return (
    <div style={{display:'grid', gap:16, gridTemplateColumns:'1fr 1fr', alignItems:'start'}}>
      <Chat />
      <div style={{border:'1px solid #ddd', borderRadius:12, padding:12}}>
        <h3>RAH IDs</h3>
        <div>RAH ID: <input value={rahId} onChange={e => setRahId(e.target.value)} /></div>
        <div>Details: <input value={details} onChange={e => setDetails(e.target.value)} /></div>
        <div>Category: <input value={category} onChange={e => setCategory(e.target.value)} /></div>
        <button onClick={createRah} disabled={busy}>{busy ? 'Saving...' : 'Create'}</button>

        <table border={1} cellPadding={6} style={{marginTop:16, width:'100%'}}>
          <thead><tr><th>RAH ID</th><th>Details</th><th>Category</th><th>Description?</th></tr></thead>
          <tbody>
            {list.map(r => (
              <tr key={r.rah_id}>
                <td>{r.rah_id.toFixed(2)}</td>
                <td>{r.details}</td>
                <td>{r.category}</td>
                <td>{r.has_description ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
