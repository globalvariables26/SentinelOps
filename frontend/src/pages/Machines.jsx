import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import api from '../api/client';

const apiBase=import.meta.env.VITE_API_URL||'http://localhost:8000/api';

export default function Machines(){
  const [rows,setRows]=useState([]); const [error,setError]=useState('');
  useEffect(()=>{api.get('/machines').then(r=>setRows(r.data)).catch(e=>setError(e.response?.data?.detail||'Unable to load machines.'))},[]);
  return <section className="panel">
    <div className="panel-head"><div><h2>Machine Passport</h2><span className="muted">Health, QR access and service history</span></div><span className="badge">{rows.length} machines</span></div>
    {error&&<p className="error">{error}</p>}
    <div className="cards">{rows.map(m=><article className="machine" key={m.id}>
      <div><b>{m.code}</b><span>{m.model}</span><span>{m.site_name} · {m.serial}</span></div>
      <strong>{Math.round(m.health_score)}<small> health</small></strong>
      <em>{m.status} · {m.criticality}</em>
      <div className="actions" style={{gridColumn:'1/-1'}}>
        <Link className="button" to={`/machines/${m.id}`}>Digital Passport</Link>
        <a className="button" href={`${apiBase}/machines/${m.id}/qr.png`} target="_blank" rel="noreferrer">QR Code</a>
        <Link className="button primary" to={`/requests/new?machine=${m.id}`}>Raise Service Request</Link>
      </div>
    </article>)}</div>
  </section>;
}
