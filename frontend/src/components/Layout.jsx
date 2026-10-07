import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const NAV_BY_ROLE = {
  ADMIN: [
    ['/', 'Control Tower'],
    ['/requests', 'Service Requests'],
    ['/exceptions', 'Exceptions'],
    ['/machines', 'Machines'],
    ['/technicians', 'Technicians'],
    ['/metrics', 'Metrics'],
  ],
  MANAGER: [
    ['/', 'Control Tower'],
    ['/requests', 'Service Requests'],
    ['/exceptions', 'Exceptions'],
    ['/machines', 'Machines'],
    ['/technicians', 'Technicians'],
    ['/metrics', 'Metrics'],
  ],
  SUPERVISOR: [
    ['/', 'Control Tower'],
    ['/requests', 'Service Requests'],
    ['/exceptions', 'Exceptions'],
    ['/machines', 'Machines'],
    ['/metrics', 'Metrics'],
  ],
  TECHNICIAN: [
    ['/', 'My Operations'],
    ['/requests', 'My Jobs'],
    ['/machines', 'Machines'],
  ],
  CUSTOMER: [
    ['/', 'Service Status'],
    ['/requests', 'My Requests'],
    ['/machines', 'My Machines'],
  ],
};

export const ROLE_ALLOWED_PATHS = {
  ADMIN: ['/', '/requests', '/exceptions', '/machines', '/technicians', '/metrics'],
  MANAGER: ['/', '/requests', '/exceptions', '/machines', '/technicians', '/metrics'],
  SUPERVISOR: ['/', '/requests', '/exceptions', '/machines', '/metrics'],
  TECHNICIAN: ['/', '/requests', '/machines'],
  CUSTOMER: ['/', '/requests', '/machines'],
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const links = NAV_BY_ROLE[user?.role] || [];

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="pulse" />SentinelOps</div>
        <div className="sub">SERVICE COMMAND CENTER</div>

        <nav aria-label="Primary navigation">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'}>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="side-bottom">
          <div className="user">
            <b>{user?.name}</b>
            <small>{user?.role}</small>
          </div>
          <button
            onClick={() => {
              logout();
              navigate('/login');
            }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main>
        <header>
          <div>
            <span className="eyebrow">LIVE OPERATIONS</span>
            <h1>Exception-first service control</h1>
          </div>
          <div className="live">
            <span />
            <span>{user?.role || 'USER'} workspace</span>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
