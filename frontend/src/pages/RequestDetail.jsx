import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';

export default function RequestDetail() {
  const { id } = useParams();
  const { user } = useAuth();

  const [data, setData] = useState(null);
  const [selectedPlan, setSelectedPlan] = useState('BEST_FIT');
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isManager =
    user?.role === 'MANAGER' ||
    user?.role === 'ADMIN';

  async function loadRequest() {
    setLoading(true);
    setError('');

    try {
      const response = await api.get(
        `/requests/${id}`
      );

      const request = response.data;

      setData(request);

      /*
       * Automatically select the recommended plan.
       */
      const recommended =
        request.plans?.find(
          (plan) => plan.is_recommended
        );

      if (recommended) {
        setSelectedPlan(
          recommended.plan_type
        );
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Unable to load service request.'
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRequest();
  }, [id]);

  async function approveRequest() {
    if (!safetyConfirmed) {
      setError(
        'Please confirm the safety requirements before approval.'
      );
      return;
    }

    setActionLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.post(
        `/requests/${id}/approve`,
        {
          plan_type: selectedPlan,
          safety_confirmed: true,
        }
      );

      setSuccess(
        response.data?.message ||
          'Service request approved and assigned successfully.'
      );

      await loadRequest();
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Approval failed.'
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function rejectRequest() {
    const reason = window.prompt(
      'Enter the reason for rejecting this request:'
    );

    if (!reason?.trim()) {
      return;
    }

    setActionLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.post(
        `/requests/${id}/reject`,
        {
          reason: reason.trim(),
        }
      );

      setSuccess(
        response.data?.message ||
          'Service request rejected.'
      );

      await loadRequest();
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Rejection failed.'
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function holdRequest() {
    const reason = window.prompt(
      'Enter the reason for putting this request on hold:'
    );

    if (!reason?.trim()) {
      return;
    }

    setActionLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.post(
        `/requests/${id}/hold`,
        {
          reason: reason.trim(),
        }
      );

      setSuccess(
        response.data?.message ||
          'Service request placed on hold.'
      );

      await loadRequest();
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Unable to place request on hold.'
      );
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="loading">
        Loading request…
      </div>
    );
  }

  if (!data) {
    return (
      <section className="panel">
        <b className="error">
          Request could not be loaded.
        </b>
      </section>
    );
  }

  const selected =
    data.plans?.find(
      (plan) =>
        plan.plan_type === selectedPlan
    );

  const canApprove =
    isManager &&
    data.status === 'PENDING_APPROVAL';

  return (
    <section>
      {/* ------------------------------------------------ */}
      {/* HEADER */}
      {/* ------------------------------------------------ */}

      <div className="hero">
        <div>
          <span className="eyebrow">
            SERVICE REQUEST
          </span>

          <h1>
            {data.code} · {data.machine?.code}
          </h1>

          <p>
            {data.description}
          </p>
        </div>

        <div className="actions">
          <Link
            className="button"
            to="/requests"
          >
            ← Requests
          </Link>

          <span className="status">
            {data.status}
          </span>

          <span
            className={`risk ${String(
              data.sla?.risk_level ||
                'SAFE'
            ).toLowerCase()}`}
          >
            {data.sla?.risk_level ||
              'SAFE'}
          </span>
        </div>
      </div>

      {/* ------------------------------------------------ */}
      {/* ERROR / SUCCESS */}
      {/* ------------------------------------------------ */}

      {error && (
        <div
          className="check fail"
          style={{ marginBottom: 15 }}
        >
          {error}
        </div>
      )}

      {success && (
        <div
          className="check pass"
          style={{ marginBottom: 15 }}
        >
          {success}
        </div>
      )}

      {/* ------------------------------------------------ */}
      {/* REQUEST SUMMARY */}
      {/* ------------------------------------------------ */}

      <div className="grid two">
        <section className="panel">
          <div className="panel-head">
            <h2>Request Summary</h2>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>Machine</span>
              <b>
                {data.machine?.code}
              </b>
            </div>

            <div className="metric">
              <span>Fault</span>
              <b>
                {data.fault_category?.name}
              </b>
            </div>

            <div className="metric">
              <span>Priority</span>
              <b>
                {data.effective_priority ||
                  data.priority}
              </b>
            </div>

            <div className="metric">
              <span>Readiness</span>
              <b>
                {Math.round(
                  data.readiness?.score ||
                    0
                )}
                %
              </b>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>SLA</h2>

            <span
              className={`risk ${String(
                data.sla?.risk_level ||
                  'SAFE'
              ).toLowerCase()}`}
            >
              {data.sla?.risk_level ||
                'SAFE'}
            </span>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>Risk ratio</span>
              <b>
                {data.sla?.risk_ratio ??
                  '—'}
              </b>
            </div>

            <div className="metric">
              <span>Response due</span>
              <b>
                {data.sla?.response_due_at
                  ? new Date(
                      data.sla.response_due_at
                    ).toLocaleString()
                  : '—'}
              </b>
            </div>

            <div className="metric">
              <span>SLA due</span>
              <b>
                {data.sla?.sla_due_at
                  ? new Date(
                      data.sla.sla_due_at
                    ).toLocaleString()
                  : '—'}
              </b>
            </div>

            <div className="metric">
              <span>Location</span>
              <b>
                {data.site?.name}
              </b>
            </div>
          </div>
        </section>
      </div>

      {/* ------------------------------------------------ */}
      {/* READINESS */}
      {/* ------------------------------------------------ */}

      <section className="panel">
        <div className="panel-head">
          <h2>Readiness Gate</h2>

          <strong className="score small">
            {Math.round(
              data.readiness?.score || 0
            )}
            %
          </strong>
        </div>

        <div className="checks">
          {(data.readiness?.passed || []).map(
            (item, index) => (
              <div
                className="check pass"
                key={`pass-${index}`}
              >
                ✓ {item}
              </div>
            )
          )}

          {(data.readiness?.missing || []).map(
            (item, index) => (
              <div
                className="check fail"
                key={`missing-${index}`}
              >
                ! {item}
              </div>
            )
          )}
        </div>
      </section>

      {/* ------------------------------------------------ */}
      {/* MATCHING PLANS */}
      {/* ------------------------------------------------ */}

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>
              Explainable Matching Plans
            </h2>

            <p className="muted">
              Choose the technician dispatch
              strategy that best fits the
              operational situation.
            </p>
          </div>

          <span className="badge">
            {data.plans?.length || 0} plans
          </span>
        </div>

        <div className="plan-grid">
          {(data.plans || []).map(
            (plan) => {
              const selected =
                selectedPlan ===
                plan.plan_type;

              return (
                <button
                  type="button"
                  key={plan.plan_type}
                  className={`plan-card ${
                    selected
                      ? 'selected'
                      : ''
                  }`}
                  onClick={() =>
                    canApprove &&
                    setSelectedPlan(
                      plan.plan_type
                    )
                  }
                  disabled={!canApprove}
                >
                  <div className="plan-top">
                    <div>
                      <span className="eyebrow">
                        {plan.badge}
                      </span>

                      <h3>
                        {plan.title}
                      </h3>
                    </div>

                    <div className="plan-score">
                      {Math.round(
                        plan.score || 0
                      )}
                    </div>
                  </div>

                  <p className="plan-explanation">
                    {plan.explanation}
                  </p>

                  <div className="plan-facts">
                    <div>
                      <span>
                        Technician
                      </span>
                      <b>
                        {
                          plan.technician
                            ?.code
                        }{' '}
                        ·{' '}
                        {
                          plan.technician
                            ?.name
                        }
                      </b>
                    </div>

                    <div>
                      <span>
                        ETA
                      </span>
                      <b>
                        {Math.round(
                          plan.eta_minutes ||
                            0
                        )}{' '}
                        min
                      </b>
                    </div>

                    <div>
                      <span>
                        SLA
                      </span>
                      <b>
                        {plan.sla_outcome}
                      </b>
                    </div>

                    <div>
                      <span>
                        Parts
                      </span>
                      <b>
                        {plan.part_source}
                      </b>
                    </div>

                    <div>
                      <span>
                        Workload
                      </span>
                      <b>
                        {
                          plan.today_jobs
                        }{' '}
                        jobs today
                      </b>
                    </div>

                    <div>
                      <span>
                        Cost
                      </span>
                      <b>
                        {plan.cost_bucket}
                      </b>
                    </div>
                  </div>

                  <div className="score-breakdown">
                    <span>
                      Skill{' '}
                      {Math.round(
                        plan.breakdown
                          ?.skill_match ||
                          0
                      )}
                    </span>

                    <span>
                      Availability{' '}
                      {Math.round(
                        plan.breakdown
                          ?.availability ||
                          0
                      )}
                    </span>

                    <span>
                      Distance{' '}
                      {Math.round(
                        plan.breakdown
                          ?.distance_and_eta ||
                          0
                      )}
                    </span>

                    <span>
                      Familiarity{' '}
                      {Math.round(
                        plan.breakdown
                          ?.machine_familiarity ||
                          0
                      )}
                    </span>
                  </div>

                  {selected && (
                    <div className="selected-plan">
                      ✓ Selected
                    </div>
                  )}
                </button>
              );
            }
          )}
        </div>
      </section>

      {/* ------------------------------------------------ */}
      {/* IMPACT CHAIN */}
      {/* ------------------------------------------------ */}

      <section className="panel">
        <div className="panel-head">
          <h2>
            Spare-Part Impact Chain
          </h2>
        </div>

        <div className="chain">
          {(
            data.impact_chain?.chain ||
            [
              'Part shortage',
              'Job delay',
              'Machine downtime',
              'SLA risk',
              'Customer impact',
            ]
          ).map((item, index) => (
            <div key={index}>
              {item}

              {index <
                (
                  data.impact_chain
                    ?.chain || []
                ).length -
                  1 && (
                <span>→</span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------ */}
      {/* ACTIVE ASSIGNMENT */}
      {/* ------------------------------------------------ */}

      {data.active_assignment && (
        <section className="panel">
          <div className="panel-head">
            <h2>
              Active Assignment
            </h2>

            <span className="status">
              {
                data.active_assignment
                  .status
              }
            </span>
          </div>

          <div className="metric-grid">
            <div className="metric">
              <span>
                Technician
              </span>
              <b>
                {
                  data.active_assignment
                    .technician_code
                }
              </b>
            </div>

            <div className="metric">
              <span>
                Match score
              </span>
              <b>
                {Math.round(
                  data.active_assignment
                    .match_score || 0
                )}
              </b>
            </div>

            <div className="metric">
              <span>
                ETA
              </span>
              <b>
                {Math.round(
                  data.active_assignment
                    .eta_minutes || 0
                )}{' '}
                min
              </b>
            </div>

            <div className="metric">
              <span>
                Ack due
              </span>
              <b>
                {
                  data.active_assignment
                    .ack_due_at
                    ? new Date(
                        data
                          .active_assignment
                          .ack_due_at
                      ).toLocaleTimeString()
                    : '—'
                }
              </b>
            </div>
          </div>
        </section>
      )}

      {/* ------------------------------------------------ */}
      {/* MANAGER APPROVAL */}
      {/* ------------------------------------------------ */}

      {canApprove && (
        <section className="approval-panel">
          <div>
            <span className="eyebrow">
              MANAGER ACTION
            </span>

            <h2>
              Approve & Dispatch
            </h2>

            <p>
              Selected plan:{' '}
              <strong>
                {selected?.title ||
                  selectedPlan}
              </strong>
            </p>

            {selected && (
              <p className="muted">
                Technician:{' '}
                {
                  selected.technician?.code
                }{' '}
                ·{' '}
                {
                  selected.technician?.name
                }
              </p>
            )}
          </div>

          <label className="approval-check">
            <input
              type="checkbox"
              checked={
                safetyConfirmed
              }
              onChange={(event) =>
                setSafetyConfirmed(
                  event.target.checked
                )
              }
            />

            <span>
              I confirm the machine/site
              safety requirements have been
              reviewed and this dispatch is
              safe to approve.
            </span>
          </label>

          <div className="actions">
            <button
              className="button primary"
              type="button"
              disabled={
                actionLoading ||
                !safetyConfirmed
              }
              onClick={approveRequest}
            >
              {actionLoading
                ? 'Processing…'
                : 'Approve & Assign'}
            </button>

            <button
              className="button"
              type="button"
              disabled={actionLoading}
              onClick={holdRequest}
            >
              Put On Hold
            </button>

            <button
              className="button"
              type="button"
              disabled={actionLoading}
              onClick={rejectRequest}
            >
              Reject
            </button>
          </div>
        </section>
      )}
    </section>
  );
}