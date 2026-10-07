import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState('manager@sentinelops.com');
  const [password, setPassword] = useState('manager123');
  const [err, setErr] = useState('');

  const creds = [
    ['Manager', 'manager@sentinelops.com', 'manager123'],
    ['Supervisor', 'supervisor@sentinelops.com', 'supervisor123'],
    ['Technician', 'tech07@sentinelops.com', 'tech123'],
    ['Customer', 'customer@apex.com', 'customer123'],
    ['Admin', 'admin@sentinelops.com', 'admin123'],
  ];

  return (
    <div className="login">
      <div className="login-card">
        <div className="brand big"><span className="pulse" />SentinelOps</div>
        <p className="muted">Exception-first industrial service command center</p>

        <form onSubmit={async e => {
          e.preventDefault();
          setErr('');
          try {
            await login(email, password);
            nav('/');
          } catch (x) {
            setErr(x.response?.data?.detail || 'Login failed');
          }
        }}>
          <label>Email<input value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} /></label>
          {err && <div className="error">{err}</div>}
          <button className="primary">Enter command center</button>
        </form>

        <div className="demo">
          <span>Demo credentials</span>
          {creds.map(c => (
            <button key={c[0]} type="button" onClick={() => {
              setEmail(c[1]);
              setPassword(c[2]);
              setErr('');
            }}>
              {c[0]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
