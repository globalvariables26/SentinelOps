import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../api/client';

export default function QRMachinePassport() {
  const { token } = useParams();

  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    api
      .get(`/machines/qr/${token}`)
      .then((response) => {
        if (mounted) {
          setData(response.data);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(
            err.response?.data?.detail ||
              'This machine QR is invalid or unavailable.'
          );
        }
      });

    return () => {
      mounted = false;
    };
  }, [token]);

  /* Invalid QR */
  if (error) {
    return (
      <div className="login">
        <section className="login-card">
          <div className="brand big">
            <span className="pulse" />
            SentinelOps
          </div>

          <div className="eyebrow" style={{ marginTop: 20 }}>
            MACHINE QR
          </div>

          <h1>Machine Not Found</h1>

          <p className="error">
            {error}
          </p>

          <div
            className="actions"
            style={{ marginTop: 20 }}
          >
            <Link className="button" to="/login">
              Sign in
            </Link>
          </div>
        </section>
      </div>
    );
  }

  /* Loading */
  if (!data) {
    return (
      <div className="loading">
        Loading machine passport…
      </div>
    );
  }

  const machine = data.machine || {};
  const timeline = data.timeline || [];
  const metrics = data.metrics || {};

  return (
    <div className="login">
      <section
        className="login-card"
        style={{
          width: 'min(900px, 100%)',
        }}
      >
        {/* Header */}
        <div className="brand">
          <span className="pulse" />
          SentinelOps
        </div>

        <div
          className="eyebrow"
          style={{ marginTop: 25 }}
        >
          SCAN RESULT · DIGITAL MACHINE PASSPORT
        </div>

        <h1>{machine.code}</h1>

        <p>
          {machine.model} · {machine.serial} ·{' '}
          {machine.site_name}
        </p>

        {/* Machine information */}
        <div
          className="metric-grid"
          style={{ marginTop: 20 }}
        >
          <div className="metric">
            <span>Health</span>

            <b>
              {Math.round(machine.health_score || 0)}
              /100
            </b>
          </div>

          <div className="metric">
            <span>Status</span>

            <b>
              {machine.status || 'Unknown'}
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

        {/* Reliability */}
        <div
          className="panel"
          style={{ marginTop: 15 }}
        >
          <div className="panel-head">
            <h2>Machine health</h2>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>MTBF</span>
              <b>
                {metrics.mtbf_hours ?? 'N/A'}
              </b>
            </div>

            <div className="metric">
              <span>MTTR</span>
              <b>
                {metrics.mttr_hours ?? 'N/A'}
              </b>
            </div>

            <div className="metric">
              <span>Downtime</span>
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

        {/* Service history */}
        <div
          className="panel"
          style={{ marginTop: 15 }}
        >
          <div className="panel-head">
            <h2>Recent service history</h2>

            <span className="muted">
              {timeline.length} records
            </span>
          </div>

          {timeline.length === 0 ? (
            <p className="muted">
              No service history yet.
            </p>
          ) : (
            timeline
              .slice(0, 5)
              .map((record) => (
                <div
                  className="exception"
                  key={record.id}
                >
                  <div>
                    <b>
                      {record.code} · {record.fault}
                    </b>

                    <p>
                      {record.summary ||
                        'Service request recorded.'}
                    </p>
                  </div>

                  <span className="status">
                    {record.status}
                  </span>
                </div>
              ))
          )}
        </div>

        {/* Breakdown action */}
        <div
          className="actions"
          style={{ marginTop: 20 }}
        >
          <Link
            className="button primary"
            to={`/requests/new?machine=${machine.id}`}
          >
            Report breakdown
          </Link>

          <Link
            className="button"
            to="/login"
          >
            Sign in
          </Link>
        </div>
      </section>
    </div>
  );
}