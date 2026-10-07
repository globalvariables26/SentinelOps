import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../api/client';

const apiBase =
  import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function MachinePassport() {
  const { id } = useParams();

  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    api
      .get(`/machines/${id}/passport`)
      .then((response) => {
        if (mounted) {
          setData(response.data);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(
            err.response?.data?.detail ||
              'Unable to load machine passport.'
          );
        }
      });

    return () => {
      mounted = false;
    };
  }, [id]);

  if (error) {
    return (
      <section className="panel">
        <b className="error">{error}</b>
        <div className="actions" style={{ marginTop: 15 }}>
          <Link className="button" to="/machines">
            ← Machines
          </Link>
        </div>
      </section>
    );
  }

  if (!data) {
    return (
      <div className="loading">
        Loading machine passport…
      </div>
    );
  }

  const machine = data.machine || {};
  const metrics = data.metrics || {};
  const timeline = data.timeline || [];
  const repeatFailure = data.repeat_failure_alert || {};

  return (
    <section>
      {/* Header */}
      <div className="hero">
        <div>
          <div className="eyebrow">
            DIGITAL MACHINE PASSPORT
          </div>

          <h1>{machine.code}</h1>

          <p>
            {machine.model} · Serial {machine.serial} ·{' '}
            {machine.site_name}
          </p>
        </div>

        <div className="actions">
          <Link className="button" to="/machines">
            ← Machines
          </Link>

          <Link
            className="button primary"
            to={`/requests/new?machine=${machine.id}`}
          >
            Raise Service Request
          </Link>
        </div>
      </div>

      {/* Machine identity + QR */}
      <div className="two grid">
        <div className="panel">
          <div className="panel-head">
            <h2>Machine identity</h2>
            <span className="status">
              {machine.status}
            </span>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>Health</span>
              <b>
                {Math.round(machine.health_score || 0)}
                /100
              </b>
            </div>

            <div className="metric">
              <span>Health status</span>
              <b>
                {machine.health_status || 'Unknown'}
              </b>
            </div>

            <div className="metric">
              <span>Criticality</span>
              <b>
                {machine.criticality || 'Unknown'}
              </b>
            </div>

            <div className="metric">
              <span>Contract</span>
              <b>
                {machine.contract_active
                  ? 'Active'
                  : 'Inactive'}
              </b>
            </div>
          </div>
        </div>

        {/* QR */}
        <div className="panel">
          <div className="panel-head">
            <h2>QR access</h2>

            <span className="muted">
              Scan to open passport
            </span>
          </div>

          <div className="qr-box">
            <img
              src={`${apiBase}/machines/${machine.id}/qr.png`}
              alt={`QR code for ${machine.code}`}
              style={{
                width: 180,
                height: 180,
                objectFit: 'contain',
                background: '#ffffff',
                borderRadius: 8,
                padding: 8,
              }}
            />

            <div>
              <b>{machine.code}</b>

              <p className="muted">
                Use this QR on the physical machine tag.
              </p>

              <div className="actions">
                <a
                  className="button"
                  href={`${apiBase}/machines/${machine.id}/qr.png`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open QR image
                </a>

                <Link
                  className="button primary"
                  to={`/requests/new?machine=${machine.id}`}
                >
                  Report breakdown
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Reliability */}
      <div className="two grid">
        <div className="panel">
          <div className="panel-head">
            <h2>Reliability metrics</h2>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>MTBF</span>
              <b>
                {metrics.mtbf_hours ?? 'N/A'}
              </b>
            </div>

            <div className="metric">
              <span>MTTR (h)</span>
              <b>
                {metrics.mttr_hours ?? 'N/A'}
              </b>
            </div>

            <div className="metric">
              <span>Downtime (h)</span>
              <b>
                {metrics.total_downtime_hours ?? 0}
              </b>
            </div>

            <div className="metric">
              <span>Parts replaced</span>
              <b>
                {metrics.parts_replaced_count ?? 0}
              </b>
            </div>
          </div>
        </div>

        {/* Failure prevention */}
        <div className="panel">
          <div className="panel-head">
            <h2>Failure prevention</h2>
          </div>

          {repeatFailure.active ? (
            <div className="check fail">
              {repeatFailure.reason}
            </div>
          ) : (
            <div className="check pass">
              No active repeat-failure alert.
            </div>
          )}

          <p className="muted">
            Next maintenance:{' '}
            {metrics.next_maintenance_window ||
              'Insufficient data'}
          </p>
        </div>
      </div>

      {/* Service history */}
      <div className="panel">
        <div className="panel-head">
          <h2>Service history</h2>

          <span className="muted">
            {timeline.length} records
          </span>
        </div>

        {timeline.length === 0 ? (
          <p className="muted">
            No service history yet.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Fault</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>

              <tbody>
                {timeline.map((record) => (
                  <tr key={record.id}>
                    <td>{record.code}</td>

                    <td>{record.fault}</td>

                    <td>{record.priority}</td>

                    <td>{record.status}</td>

                    <td>
                      {record.created_at
                        ? new Date(
                            record.created_at
                          ).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}