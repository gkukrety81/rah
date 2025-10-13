import React, { useEffect, useState } from 'react'
import Login from './Login'
import Landing from './Landing'
import Users from './Users'

function authed(){ return !!localStorage.getItem('token') }

export default function App(){
  const [isAuthed, setIsAuthed] = useState(authed())
  const [tab, setTab] = useState(window.location.hash)

  useEffect(()=>{
    const h = () => setTab(window.location.hash)
    window.addEventListener('hashchange', h)
    return () => window.removeEventListener('hashchange', h)
  }, [])

  if(!isAuthed) return <Login onLogin={()=>setIsAuthed(true)} />

  if(tab==='#users') return (
    <div style={{fontFamily:'sans-serif'}}>
      <Nav onLogout={()=>{localStorage.removeItem('token'); location.reload()}} />
      <Users />
    </div>
  )

  return (
    <div style={{fontFamily:'sans-serif'}}>
      <Nav onLogout={()=>{localStorage.removeItem('token'); location.reload()}} />
      <div style={{padding:20}}>
        <Landing />
      </div>
    </div>
  )
}

function Nav({onLogout}:{onLogout:()=>void}){
  return (
    <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', padding:'12px 20px', borderBottom:'1px solid #eee'}}>
      <div style={{display:'flex', gap:16}}>
        <b>RAH Manager</b>
        <a href="#">Home</a>
        <a href="#users">User Management</a>
      </div>
      <button onClick={onLogout}>Logout</button>
    </div>
  )
}
