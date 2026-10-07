import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout, { ROLE_ALLOWED_PATHS } from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Requests from './pages/Requests';
import RequestDetail from './pages/RequestDetail';
import Exceptions from './pages/Exceptions';
import Machines from './pages/Machines';
import MachinePassport from './pages/MachinePassport';
import QRMachinePassport from './pages/QRMachinePassport';
import Technicians from './pages/Technicians';
import Metrics from './pages/Metrics';
import NewRequest from './pages/NewRequest';

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="loading">Starting SentinelOps…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  const allowed = ROLE_ALLOWED_PATHS[user.role] || ['/'];
  const rootPath = location.pathname === '/' ? '/' : `/${location.pathname.split('/')[1]}`;
  const isRequestDetail = location.pathname.startsWith('/requests/');
  const pathAllowed = allowed.includes(rootPath) && (!isRequestDetail || allowed.includes('/requests'));

  if (!pathAllowed) {
    return <Navigate to="/" replace />;
  }

  return <Layout><Outlet /></Layout>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/m/:token" element={<QRMachinePassport />} />
        <Route element={<Protected />}>
          <Route index element={<Dashboard />} />
          <Route path="requests" element={<Requests />} />
          <Route path="requests/:id" element={<RequestDetail />} />
          <Route path="exceptions" element={<Exceptions />} />
          <Route path="requests/new" element={<NewRequest />} />
          <Route path="machines" element={<Machines />} />
          <Route path="machines/:id" element={<MachinePassport />} />
          <Route path="technicians" element={<Technicians />} />
          <Route path="metrics" element={<Metrics />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
