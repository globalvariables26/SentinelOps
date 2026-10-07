import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import api from '../api/client';

const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export default function NewRequest() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const machineFromUrl = searchParams.get('machine');

  const [machines, setMachines] = useState([]);
  const [faultCategories, setFaultCategories] = useState([]);

  const [machineId, setMachineId] = useState(
    machineFromUrl ? String(machineFromUrl) : ''
  );
  const [faultCategoryId, setFaultCategoryId] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [description, setDescription] = useState('');

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const [result, setResult] = useState(null);

  /*
   * Load machines and fault categories.
   */
  useEffect(() => {
    let mounted = true;

    async function loadFormData() {
      setLoading(true);
      setError('');

      try {
        const [machinesResponse, faultsResponse] =
          await Promise.all([
            api.get('/machines'),
            api.get('/requests/fault-categories'),
          ]);

        if (!mounted) return;

        setMachines(machinesResponse.data || []);
        setFaultCategories(faultsResponse.data || []);

        /*
         * If the URL contains ?machine=ID,
         * keep that machine selected.
         */
        if (machineFromUrl) {
          const matchingMachine = (
            machinesResponse.data || []
          ).find(
            (machine) =>
              String(machine.id) === String(machineFromUrl)
          );

          if (matchingMachine) {
            setMachineId(String(matchingMachine.id));
          }
        }
      } catch (err) {
        if (!mounted) return;

        setError(
          err.response?.data?.detail ||
            'Unable to load service-request data.'
        );
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadFormData();

    return () => {
      mounted = false;
    };
  }, [machineFromUrl]);

  const selectedMachine = useMemo(() => {
    return machines.find(
      (machine) =>
        String(machine.id) === String(machineId)
    );
  }, [machines, machineId]);

  const selectedFault = useMemo(() => {
    return faultCategories.find(
      (fault) =>
        String(fault.id) === String(faultCategoryId)
    );
  }, [faultCategories, faultCategoryId]);

  /*
   * Submit the real service request.
   */
  async function handleSubmit(event) {
    event.preventDefault();

    setError('');
    setResult(null);

    if (!machineId) {
      setError('Please select a machine.');
      return;
    }

    if (!faultCategoryId) {
      setError('Please select a fault category.');
      return;
    }

    if (!description.trim()) {
      setError('Please describe the problem.');
      return;
    }

    setSubmitting(true);

    try {
      const response = await api.post('/requests', {
        machine_id: Number(machineId),
        fault_category_id: Number(faultCategoryId),
        description: description.trim(),
        priority,
        source: 'WEB',
      });

      setResult(response.data);
    } catch (err) {
      const detail = err.response?.data?.detail;

      if (Array.isArray(detail)) {
        setError(
          detail
            .map((item) => item.msg || String(item))
            .join(', ')
        );
      } else {
        setError(
          detail ||
            'Unable to create the service request.'
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <section className="panel">
        <div className="loading">
          Loading service-request form…
        </div>
      </section>
    );
  }

  /*
   * Successful request / validation result.
   */
  if (result) {
    const validation =
      result.validation_report || {};

    return (
      <section>
        <div className="hero">
          <div>
            <div className="eyebrow">
              SERVICE REQUEST
            </div>

            <h1>Request validated</h1>

            <p>
              The request was submitted to the SentinelOps
              validation workflow.
            </p>
          </div>

          <div className="actions">
            <Link
              className="button"
              to="/requests"
            >
              All Requests
            </Link>

            {result.id && (
              <Link
                className="button primary"
                to={`/requests/${result.id}`}
              >
                Open Request
              </Link>
            )}
          </div>
        </div>

        {/* Main result */}
        <div className="two grid">
          <div className="panel">
            <div className="panel-head">
              <h2>Request result</h2>

              <span className="status">
                {result.status || 'CREATED'}
              </span>
            </div>

            <div className="metric-grid">
              <div className="metric">
                <span>Request</span>
                <b>
                  {result.code || '—'}
                </b>
              </div>

              <div className="metric">
                <span>Readiness</span>
                <b>
                  {result.readiness_score ?? '—'}
                </b>
              </div>

              <div className="metric">
                <span>Effective priority</span>
                <b>
                  {result.effective_priority ||
                    priority}
                </b>
              </div>

              <div className="metric">
                <span>Risk</span>
                <b>
                  {result.risk_level ||
                    validation.risk_level ||
                    '—'}
                </b>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>SLA</h2>
            </div>

            <div className="metric-grid">
              <div className="metric">
                <span>Response due</span>
                <b>
                  {result.response_due
                    ? new Date(
                        result.response_due
                      ).toLocaleString()
                    : '—'}
                </b>
              </div>

              <div className="metric">
                <span>Target completion</span>
                <b>
                  {result.target_completion
                    ? new Date(
                        result.target_completion
                      ).toLocaleString()
                    : '—'}
                </b>
              </div>

              <div className="metric">
                <span>Risk ratio</span>
                <b>
                  {result.risk_ratio ??
                    validation.risk_ratio ??
                    '—'}
                </b>
              </div>
            </div>
          </div>
        </div>

        {/* Validation checks */}
        <div className="panel">
          <div className="panel-head">
            <h2>Validation report</h2>

            <span className="muted">
              Automated checks
            </span>
          </div>

          {Object.keys(validation).length === 0 ? (
            <p className="muted">
              No detailed validation report was returned.
            </p>
          ) : (
            <div className="validation-list">
              {Object.entries(validation).map(
                ([key, value]) => {
                  if (
                    value === null ||
                    value === undefined ||
                    typeof value === 'object'
                  ) {
                    return null;
                  }

                  const label = key
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, (char) =>
                      char.toUpperCase()
                    );

                  const passed =
                    value === true ||
                    value === 'PASS' ||
                    value === 'PASSED';

                  return (
                    <div
                      className={
                        passed
                          ? 'check pass'
                          : 'check'
                      }
                      key={key}
                    >
                      <div>
                        <b>{label}</b>

                        <span>
                          {typeof value === 'boolean'
                            ? value
                              ? 'PASS'
                              : 'FAIL'
                            : String(value)}
                        </span>
                      </div>
                    </div>
                  );
                }
              )}
            </div>
          )}
        </div>

        {/* Full validation JSON for important nested data */}
        {validation.parts && (
          <div className="panel">
            <div className="panel-head">
              <h2>Parts & inventory</h2>
            </div>

            <pre className="json-block">
              {JSON.stringify(
                validation.parts,
                null,
                2
              )}
            </pre>
          </div>
        )}

        {validation.impact_chain && (
          <div className="panel">
            <div className="panel-head">
              <h2>Impact chain</h2>
            </div>

            <pre className="json-block">
              {JSON.stringify(
                validation.impact_chain,
                null,
                2
              )}
            </pre>
          </div>
        )}

        <div className="actions">
          <button
            className="button"
            type="button"
            onClick={() => {
              setResult(null);
              setDescription('');
              setFaultCategoryId('');
              setPriority('MEDIUM');
            }}
          >
            Create Another Request
          </button>
        </div>
      </section>
    );
  }

  /*
   * New request form.
   */
  return (
    <section>
      <div className="hero">
        <div>
          <div className="eyebrow">
            SERVICE REQUEST
          </div>

          <h1>Raise Service Request</h1>

          <p>
            Create a maintenance request and run the
            operational validation checks.
          </p>
        </div>

        <div className="actions">
          <Link
            className="button"
            to="/requests"
          >
            ← Requests
          </Link>
        </div>
      </div>

      {error && (
        <div
          className="check fail"
          style={{ marginBottom: 16 }}
        >
          <div>
            <b>Request could not be submitted</b>
            <span>{error}</span>
          </div>
        </div>
      )}

      <form
        className="panel"
        onSubmit={handleSubmit}
      >
        <div className="panel-head">
          <h2>Request details</h2>

          <span className="muted">
            All fields marked * are required
          </span>
        </div>

        {/* Machine */}
        <div className="form-grid">
          <label>
            <span>Machine *</span>

            <select
              value={machineId}
              onChange={(event) =>
                setMachineId(event.target.value)
              }
              required
            >
              <option value="">
                Select machine
              </option>

              {machines.map((machine) => (
                <option
                  key={machine.id}
                  value={machine.id}
                >
                  {machine.code} — {machine.model}
                  {machine.site_name
                    ? ` — ${machine.site_name}`
                    : ''}
                </option>
              ))}
            </select>
          </label>

          {/* Fault */}
          <label>
            <span>Fault category *</span>

            <select
              value={faultCategoryId}
              onChange={(event) =>
                setFaultCategoryId(
                  event.target.value
                )
              }
              required
            >
              <option value="">
                Select fault category
              </option>

              {faultCategories.map((fault) => (
                <option
                  key={fault.id}
                  value={fault.id}
                >
                  {fault.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Selected machine preview */}
        {selectedMachine && (
          <div
            className="panel"
            style={{ marginTop: 16 }}
          >
            <div className="panel-head">
              <h2>
                Selected machine
              </h2>

              <span className="status">
                {selectedMachine.status}
              </span>
            </div>

            <div className="metric-grid">
              <div className="metric">
                <span>Machine</span>
                <b>
                  {selectedMachine.code}
                </b>
              </div>

              <div className="metric">
                <span>Site</span>
                <b>
                  {selectedMachine.site_name ||
                    '—'}
                </b>
              </div>

              <div className="metric">
                <span>Health</span>
                <b>
                  {Math.round(
                    selectedMachine.health_score ||
                      0
                  )}
                  /100
                </b>
              </div>

              <div className="metric">
                <span>Criticality</span>
                <b>
                  {selectedMachine.criticality ||
                    '—'}
                </b>
              </div>
            </div>
          </div>
        )}

        {/* Selected fault */}
        {selectedFault && (
          <div
            className="check pass"
            style={{ marginTop: 16 }}
          >
            <div>
              <b>
                {selectedFault.name}
              </b>

              {selectedFault.description && (
                <span>
                  {selectedFault.description}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Priority */}
        <label
          style={{
            display: 'block',
            marginTop: 20,
          }}
        >
          <span>Priority *</span>

          <select
            value={priority}
            onChange={(event) =>
              setPriority(event.target.value)
            }
            required
          >
            {PRIORITIES.map((value) => (
              <option
                key={value}
                value={value}
              >
                {value}
              </option>
            ))}
          </select>
        </label>

        {/* Description */}
        <label
          style={{
            display: 'block',
            marginTop: 20,
          }}
        >
          <span>
            Problem description *
          </span>

          <textarea
            value={description}
            onChange={(event) =>
              setDescription(event.target.value)
            }
            placeholder="Describe the machine problem, symptoms, and operational impact..."
            rows={7}
            required
          />

          <small className="muted">
            {description.length} characters
          </small>
        </label>

        {/* Submit */}
        <div
          className="actions"
          style={{ marginTop: 24 }}
        >
          <button
            className="button primary"
            type="submit"
            disabled={submitting}
          >
            {submitting
              ? 'Running validation…'
              : 'Submit & Validate'}
          </button>

          <Link
            className="button"
            to="/requests"
          >
            Cancel
          </Link>
        </div>
      </form>
    </section>
  );
}