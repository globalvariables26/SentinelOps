import { useEffect, useState } from 'react';
import api from '../api/client';

export default function Metrics(){
  const [d,setD]=useState(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    api.get('/dashboard/metrics')
      .then(r=>setD(r.data || {metrics:[]}))
      .catch(e=>setError(e.response?.data?.detail || e.message || 'Unable to load metrics'));
  },[]);
  if(error) return <section className="panel"><h2>Metrics unavailable</h2><p className="error">{error}</p></section>;
  if(!d) return <div className="loading">Loading metrics…</div>;
  const rows=Array.isArray(d.metrics) ? d.metrics : Object.entries(d).map(([key,value])=>({key,label:key.replaceAll('_',' '),value,description:''}));
  return <section className="panel">
    <div className="panel-head"><h2>Operational baseline</h2><span className="muted">Calculated from SentinelOps data</span></div>
    <div className="metric-grid">
      {rows.map((m)=><div className="metric" key={m.key || m.label}>
        <span>{m.label || m.key}</span>
        <b>{m.value == null ? 'N/A' : (typeof m.value === 'object' ? JSON.stringify(m.value) : String(m.value))}</b>
        {m.description && <small className="muted">{m.description}</small>}
      </div>)}
    </div>
  </section>;
}
