import {useEffect,useState} from 'react';
import api from '../api/client';
import {useAuth} from '../context/AuthContext';

export default function Exceptions(){
  const {user}=useAuth();
  const [rows,setRows]=useState([]);
  const [error,setError]=useState('');
  const load=()=>api.get('/exceptions').then(r=>{setRows(Array.isArray(r.data)?r.data:[]);setError('')}).catch(e=>setError(e.response?.data?.detail||e.message||'Unable to load exceptions'));
  useEffect(()=>{load()},[]);
  const canAct=['ADMIN','MANAGER'].includes(user?.role);
  return <section className="panel">
    <div className="panel-head"><h2>Exception Center</h2><span className="badge warn">LIVE PLAYBOOKS</span></div>
    {error && <p className="error">{error}</p>}
    {!error && rows.length===0 && <div className="empty-state"><h3>No open exceptions</h3><p className="muted">This view is live. In the demo dataset, active exceptions appear here automatically and are scoped to your role.</p></div>}
    {rows.map(x=><div className="exception large" key={x.id}>
      <div><span className={`risk ${String(x.severity||'').toLowerCase()}`}>{x.severity}</span><h3>{x.rule_code} · {x.request_code}</h3><p>{x.reason}</p><small>Owner: {x.owner_role} · Blocker: {x.blocker||'—'}</small></div>
      {canAct && <div className="actions"><button onClick={()=>api.get(`/exceptions/${x.id}/options`).then(r=>alert(JSON.stringify(r.data,null,2)))}>Simulate</button><button className="primary" onClick={()=>{const tech=x.options_snapshot?.[0]?.technician_id;if(!tech){alert('No hot-swap candidate is available for this exception.');return}api.post(`/exceptions/${x.id}/hotswap`,{technician_id:tech}).then(load).catch(e=>alert(e.response?.data?.detail||e.message))}}>Swap now</button></div>}
    </div>)}
  </section>
}
