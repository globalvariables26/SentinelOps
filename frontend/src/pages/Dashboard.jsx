import { useCallback, useEffect, useState } from 'react';
import api from '../api/client';
import Stat from '../components/Stat';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useWebSocket } from '../hooks/useWebSocket';

export default function Dashboard() {
  const [d, setD] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    return api.get('/dashboard/tower')
      .then(r => { setD(r.data || {}); setError(''); })
      .catch(e => setError(e.response?.data?.detail || e.message || 'Unable to load the control tower'));
  }, []);

  useEffect(() => { load(); }, [load]);
  useWebSocket(load);

  if (error && !d) {
    return <section className="panel"><h2>Control Tower unavailable</h2><p className="error">{error}</p><button className="primary" onClick={load}>Retry</button></section>;
  }
  if (!d) return <div className="loading">Loading control tower…</div>;

  const attention = d.attention_cards || d.attention || [];
  const jobs = d.charts?.status_distribution || d.jobs_by_status || [];
  const heat = d.heat_strip || d.sla_heat || [];

  return <>
    <section className="panel role-focus"><div><span className="eyebrow">{d.role || 'LIVE'} WORKSPACE</span><h2>{d.view_title || 'Exception-first service control'}</h2><p className="muted">{d.focus || 'Live service operations'}</p></div></section>
    <section className="stats">
      {Object.entries(d.kpis || {}).map(([k, v]) => <Stat key={k} label={k.replaceAll('_', ' ')} value={v} />)}
    </section>
    <div className="grid two">
      <section className="panel">
        <div className="panel-head"><h2>Needs attention now</h2><span className="badge warn">EXCEPTIONS</span></div>
        {attention.length === 0 && <p className="muted">No open exceptions.</p>}
        {attention.map(x => <div className="exception" key={x.id ?? x.exception_id}>
          <div><b>{x.request_code || x.code}</b><p>{x.reason || x.recommended_action}</p></div>
          <span className={`risk ${String(x.severity || x.risk_level || '').toLowerCase()}`}>{x.severity || x.risk_level}</span>
        </div>)}
      </section>
      <section className="panel chart">
        <h2>Jobs by status</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={jobs}><XAxis dataKey="status"/><YAxis/><Tooltip/><Bar dataKey="count"/></BarChart>
        </ResponsiveContainer>
      </section>
    </div>
    <section className="panel">
      <div className="panel-head"><h2>SLA heat strip</h2><span className="muted">Every active job</span></div>
      <div className="heat">
        {heat.length === 0 && <span className="muted">No active jobs.</span>}
        {heat.map(x => <div key={x.id} className={`heat-cell ${String(x.risk_level || x.level || x.color || 'safe').toLowerCase()}`} title={`${x.code}: ${x.risk_level || x.level || x.color || 'safe'}`}>{x.code}</div>)}
      </div>
    </section>
  </>;
}
