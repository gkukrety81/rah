import React, { useEffect, useState } from 'react'
const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

function authHeaders(){
  const t = localStorage.getItem('token')
  return t ? { 'Authorization': `Bearer ${t}` } : {}
}

type User = { user_id:string, first_name:string, last_name:string, username:string, email:string, branch?:string, location?:string, is_active:boolean, deleted_at?:string|null }

export default function Users(){
  const [list,setList]=useState<User[]>([])
  const [form,setForm]=useState({first_name:'',last_name:'',username:'',email:'',branch:'',location:'',password:''})
  const [busy,setBusy]=useState(false)

  async function load(){ const r=await fetch(`${API}/users`, { headers: { ...authHeaders() } }); setList(await r.json()) }
  useEffect(()=>{ load() },[])

  async function createUser(){
    setBusy(true); try{
      const r=await fetch(`${API}/users`,{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(form)})
      if(!r.ok) alert('Create failed'); await load()
    } finally { setBusy(false) }
  }

  async function softDelete(id:string){ if(!confirm('Soft delete this user?'))return; await fetch(`${API}/users/${id}`,{method:'DELETE', headers:{...authHeaders()}}); await load() }

  return (<div style={{padding:20}}>
    <h2>User Management</h2>
    <div style={{display:'flex',gap:16}}>
      <div style={{flex:1}}>
        <h3>Create User</h3>
        {['first_name','last_name','username','email','branch','location','password'].map(k=>(
          <div key={k} style={{margin:'6px 0'}}>{k}: <input type={k==='password'?'password':'text'} value={(form as any)[k]} onChange={e=>setForm({...form,[k]:e.target.value})}/></div>
        ))}
        <button onClick={createUser} disabled={busy}>{busy?'Creating...':'Create User'}</button>

        <h3 style={{marginTop:24}}>Users</h3>
        <table border={1} cellPadding={6}>
          <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Branch</th><th>Location</th><th>Active</th><th>Actions</th></tr></thead>
          <tbody>{list.map(u=>(<tr key={u.user_id}>
            <td>{u.first_name} {u.last_name}</td><td>{u.username}</td><td>{u.email}</td><td>{u.branch}</td><td>{u.location}</td><td>{u.is_active?'Yes':'No'}</td>
            <td><button onClick={()=>softDelete(u.user_id)}>Soft Delete</button></td></tr>))}</tbody>
        </table>
      </div>
    </div>
  </div>)}
