
import { useEffect, useMemo, useState } from 'react';
import * as maintenance from '../services/maintenanceService';
import './maintenanceDashboard.css';

const SECTIONS = [
    'Overview',
    'Asset Health',
    'Predictive Alerts',
    'Work Orders',
    'Asset Lifecycle',
    'AI Maintenance Agent',
];

const getArray = (data, ...keys) => {
    if (Array.isArray(data)) return data;
    for (const key of keys) {
        if (Array.isArray(data?.[key])) return data[key];
    }
    return [];
};

const getHealth = (asset) =>
    asset.health || asset.health_analysis || asset.health_result || asset;

const getScore = (asset) => {
    const h = getHealth(asset);
    return Number(h.health_score ?? h.score ?? asset.health_score ?? 0);
};

const getStatus = (asset) => {
    const h = getHealth(asset);
    return h.health_status || h.condition || h.status ||
        asset.health_status || asset.status || 'UNKNOWN';
};

const getRisk = (asset) => {
    const h = getHealth(asset);
    return h.risk_level || asset.risk_level || 'UNKNOWN';
};

const getName = (asset) =>
    asset.asset_name || asset.asset_code || asset.name || `Asset ${asset.asset_id || asset.id}`;

const dateText = (value) =>
    value ? new Date(value).toLocaleDateString('en-IN') : '—';

function Metric({ label, value, detail, tone }) {
    return (
        <div className={`maint-metric ${tone || ''}`}>
            <span>{label}</span>
            <strong>{value}</strong>
            {detail && <small>{detail}</small>}
        </div>
    );
}

function Pill({ value }) {
    const text = String(value || 'UNKNOWN').replaceAll('_', ' ');
    return <span className={`maint-pill ${String(value).toLowerCase()}`}>{text}</span>;
}

function Loading({ error, onRetry }) {
    return (
        <div className="maint-state">
            {error ? (
                <>
                    <h3>Unable to load maintenance data</h3>
                    <p>{error}</p>
                    <button onClick={onRetry}>Retry</button>
                </>
            ) : 'Loading maintenance intelligence...'}
        </div>
    );
}

export default function MaintenanceDashboard({ facilityId }) {
    const [section, setSection] = useState('Overview');
    const [analysis, setAnalysis] = useState(null);
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedAsset, setSelectedAsset] = useState('');
    const [chatInput, setChatInput] = useState('');
    const [chatMessages, setChatMessages] = useState([]);
    const [chatLoading, setChatLoading] = useState(false);
    const [form, setForm] = useState({
        issue_type: '',
        description: '',
        maintenance_date: '',
        priority: 'MEDIUM',
    });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    async function loadData() {
        setLoading(true);
        setError('');
        try {
            const [a, w] = await Promise.all([
                maintenance.analyzeFacility(facilityId),
                maintenance.getFacilityWorkOrders(facilityId),
            ]);
            setAnalysis(a);
            setOrders(getArray(w, 'work_orders', 'records', 'items'));
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        loadData();
    }, [facilityId]);

    const assets = useMemo(
        () => getArray(analysis, 'assets', 'asset_analyses', 'results'),
        [analysis]
    );

    const alerts = useMemo(
        () => getArray(analysis, 'alerts', 'maintenance_alerts'),
        [analysis]
    );

    const counts = useMemo(() => {
        const scores = assets.map(getScore);
        return {
            total: assets.length,
            healthy: assets.filter((a) => ['HEALTHY', 'GOOD'].includes(getStatus(a).toUpperCase())).length,
            attention: assets.filter((a) => ['DEGRADING', 'POOR'].includes(getStatus(a).toUpperCase())).length,
            critical: assets.filter((a) => ['CRITICAL', 'FAILED'].includes(getStatus(a).toUpperCase())).length,
            average: scores.length
                ? (scores.reduce((sum, n) => sum + n, 0) / scores.length).toFixed(1)
                : '—',
        };
    }, [assets]);

    async function submitWorkOrder(e) {
        e.preventDefault();
        if (!selectedAsset || !form.issue_type.trim()) return;

        setSaving(true);
        setMessage('');
        try {
            await maintenance.createWorkOrder(Number(selectedAsset), {
                ...form,
                maintenance_date: form.maintenance_date || null,
            });
            setMessage('Work order created successfully.');
            setForm({
                issue_type: '',
                description: '',
                maintenance_date: '',
                priority: 'MEDIUM',
            });
            await loadData();
        } catch (e) {
            setMessage(`Could not create work order: ${e.message}`);
        } finally {
            setSaving(false);
        }
    }

    async function changeOrderStatus(id, status) {
        try {
            await maintenance.updateWorkOrderStatus(id, status);
            await loadData();
        } catch (e) {
            setMessage(`Status update failed: ${e.message}`);
        }
    }
    async function sendMaintenanceMessage(e) {
        e.preventDefault();

        const question = chatInput.trim();
        if (!question || chatLoading) return;

        setChatMessages((prev) => [
            ...prev,
            { role: 'user', content: question },
        ]);

        setChatInput('');
        setChatLoading(true);

        try {
            const result = await maintenance.askMaintenanceAgent(
                facilityId,
                question
            );

            setChatMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: result.answer,
                    mode: result.mode,
                },
            ]);
        } catch (error) {
            setChatMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: `Unable to get a response: ${error.message}`,
                },
            ]);
        } finally {
            setChatLoading(false);
        }
    }
    if (loading && !analysis) return <Loading />;
    if (error && !analysis) return <Loading error={error} onRetry={loadData} />;

    return (
        <div className="maintenance">
            <div className="maint-heading">
                <div>
                    <span className="maint-eyebrow">MILESTONE 2 · PREDICTIVE MAINTENANCE</span>
                    <h2>Maintenance Intelligence</h2>
                    <p>Monitor equipment health, identify risks and manage maintenance operations.</p>
                </div>
                <button className="maint-refresh" onClick={loadData}>↻ Refresh</button>
            </div>

            <div className="maint-tabs">
                {SECTIONS.map((item) => (
                    <button
                        key={item}
                        className={section === item ? 'selected' : ''}
                        onClick={() => setSection(item)}
                    >
                        {item}
                    </button>
                ))}
            </div>

            {message && <div className="maint-message">{message}</div>}
            {error && <div className="maint-message">{error}</div>}

            {section === 'Overview' && (
                <>
                    <div className="maint-metrics">
                        <Metric label="Monitored assets" value={counts.total} detail="Equipment tracked" />
                        <Metric label="Average health" value={`${counts.average}${counts.average !== '—' ? '/100' : ''}`} detail="Across monitored assets" />
                        <Metric label="Healthy / Good" value={counts.healthy} tone="good" />
                        <Metric label="Needs attention" value={counts.attention + counts.critical} detail={`${counts.critical} critical`} tone="warning" />
                        <Metric label="Open work orders" value={orders.filter((o) => ['SCHEDULED', 'IN_PROGRESS'].includes(o.status)).length} />
                    </div>

                    <section className="maint-panel">
                        <div className="maint-panel-title">
                            <div>
                                <h3>Equipment health overview</h3>
                                <p>Current condition of monitored equipment</p>
                            </div>
                        </div>
                        <AssetTable assets={assets.slice(0, 8)} />
                        {!assets.length && <p className="maint-empty">No asset analysis data returned for this facility.</p>}
                    </section>

                    <section className="maint-panel">
                        <h3>Recent predictive alerts</h3>
                        <AlertTable alerts={alerts.slice(0, 5)} />
                        {!alerts.length && <p className="maint-empty">No maintenance alerts returned.</p>}
                    </section>
                </>
            )}

            {section === 'Asset Health' && (
                <section className="maint-panel">
                    <h3>Asset health monitoring</h3>
                    <p className="maint-subtitle">Health scores and current equipment condition</p>
                    <AssetTable assets={assets} />
                    {!assets.length && <p className="maint-empty">No assets found.</p>}
                </section>
            )}

            {section === 'Predictive Alerts' && (
                <section className="maint-panel">
                    <h3>Predictive maintenance alerts</h3>
                    <p className="maint-subtitle">Alerts generated by the Maintenance Agent</p>
                    <AlertTable alerts={alerts} />
                    {!alerts.length && <p className="maint-empty">No alerts returned by the Maintenance Agent.</p>}
                </section>
            )}

            {section === 'Work Orders' && (
                <>
                    <section className="maint-panel">
                        <h3>Create maintenance work order</h3>
                        <form className="maint-form" onSubmit={submitWorkOrder}>
                            <label>
                                Asset
                                <select value={selectedAsset} onChange={(e) => setSelectedAsset(e.target.value)} required>
                                    <option value="">Select equipment</option>
                                    {assets.map((a) => (
                                        <option key={a.asset_id || a.id} value={a.asset_id || a.id}>
                                            {getName(a)}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <label>
                                Issue type
                                <input
                                    value={form.issue_type}
                                    onChange={(e) => setForm({ ...form, issue_type: e.target.value })}
                                    placeholder="e.g. Abnormal vibration"
                                    required
                                />
                            </label>
                            <label>
                                Priority
                                <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                                    <option>LOW</option>
                                    <option>MEDIUM</option>
                                    <option>HIGH</option>
                                    <option>CRITICAL</option>
                                </select>
                            </label>
                            <label>
                                Scheduled date
                                <input
                                    type="date"
                                    value={form.maintenance_date}
                                    onChange={(e) => setForm({ ...form, maintenance_date: e.target.value })}
                                />
                            </label>
                            <label className="wide">
                                Description
                                <textarea
                                    value={form.description}
                                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                                    placeholder="Describe the maintenance requirement..."
                                />
                            </label>
                            <button type="submit" disabled={saving}>
                                {saving ? 'Creating...' : 'Create Work Order'}
                            </button>
                        </form>
                    </section>

                    <section className="maint-panel">
                        <h3>Work order management</h3>
                        <WorkOrderTable orders={orders} onStatusChange={changeOrderStatus} />
                        {!orders.length && <p className="maint-empty">No work orders found.</p>}
                    </section>
                </>
            )}

            {section === 'Asset Lifecycle' && (
                <section className="maint-panel">
                    <h3>Asset lifecycle tracking</h3>
                    <p className="maint-subtitle">Equipment age, service history and expected end of life</p>
                    <div className="maint-table-wrap">
                        <table>
                            <thead>
                                <tr><th>Asset</th><th>Lifecycle</th><th>Age</th><th>Expected end of life</th><th>Life used</th><th>Maintenance records</th></tr>
                            </thead>
                            <tbody>
                                {assets.map((a) => {
                                    const l = a.lifecycle || a.lifecycle_analysis || {};

                                    return (
                                        <tr key={a.asset_id || a.id}>
                                            <td><strong>{getName(a)}</strong></td>

                                            <td>
                                                <Pill value={l.lifecycle_status || 'UNKNOWN'} />
                                            </td>

                                            <td>
                                                {l.asset_age_years != null
                                                    ? `${Number(l.asset_age_years).toFixed(1)} yrs`
                                                    : '—'}
                                            </td>

                                            <td>{l.expected_end_of_life || '—'}</td>

                                            <td>
                                                {l.life_used_percentage != null
                                                    ? `${Number(l.life_used_percentage).toFixed(1)}%`
                                                    : '—'}
                                            </td>

                                            <td>{l.maintenance_history_count ?? '—'}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    {!assets.length && <p className="maint-empty">No lifecycle data returned.</p>}
                </section>
            )}
            {section === 'AI Maintenance Agent' && (
                <section className="maint-panel">
                    <div className="maint-panel-title">
                        <div>
                            <h3>AI Maintenance Agent</h3>
                            <p>
                                Ask questions about equipment health, predictive alerts,
                                maintenance schedules and work orders.
                            </p>
                        </div>
                        <Pill value="AI ASSISTANT" />
                    </div>

                    <div style={{
                        minHeight: '320px',
                        maxHeight: '450px',
                        overflowY: 'auto',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '14px',
                    }}>
                        {chatMessages.length === 0 && (
                            <div className="maint-suggestions">
                                <h3>How can I help with maintenance?</h3>
                                <p>Choose a question to get started</p>

                                <div className="maint-suggestion-list">
                                    {[
                                        'Which assets need immediate maintenance attention?',
                                        'Explain the critical equipment alerts.',
                                        'Which assets have stale telemetry?',
                                        'What maintenance actions should we prioritize?',
                                        'Show me the assets with the lowest health scores.',
                                    ].map((question) => (
                                        <button
                                            key={question}
                                            type="button"
                                            className="maint-suggestion"
                                            disabled={chatLoading}
                                            onClick={() => setChatInput(question)}
                                        >
                                            {question}
                                            <span>→</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                        {chatMessages.map((msg, index) => (
                            <div
                                key={index}
                                style={{
                                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                    maxWidth: '85%',
                                    padding: '14px 18px',
                                    borderRadius: '12px',
                                    background: msg.role === 'user' ? '#263f65' : '#182638',
                                    color: '#fff',
                                    whiteSpace: 'pre-wrap',
                                    lineHeight: 1.6,
                                }}
                            >
                                <strong>
                                    {msg.role === 'user' ? 'You' : 'Maintenance AI'}
                                </strong>
                                <div>{msg.content.replace(/\\\*/g, '**').replace(/\*\*(.*?)\*\*/g, '$1')}</div>
                                {msg.mode && (
                                    <small style={{ opacity: 0.65 }}>
                                        Powered by {msg.mode}
                                    </small>
                                )}
                            </div>
                        ))}

                        {chatLoading && (
                            <div className="maint-empty">
                                Maintenance Agent is analysing facility data...
                            </div>
                        )}
                    </div>

                    <form
                        onSubmit={sendMaintenanceMessage}
                        style={{
                            display: 'flex',
                            gap: '10px',
                            marginTop: '16px',
                        }}
                    >
                        <input
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            placeholder="Ask your Maintenance AI Agent..."
                            disabled={chatLoading}
                            style={{ flex: 1 }}
                        />
                        <button type="submit" disabled={chatLoading || !chatInput.trim()}>
                            {chatLoading ? 'Thinking...' : 'Send'}
                        </button>
                    </form>
                </section>
            )}
        </div>
    );
}

function AssetTable({ assets }) {
    return (
        <div className="maint-table-wrap">
            <table>
                <thead>
                    <tr><th>Equipment</th><th>Health score</th><th>Condition</th><th>Risk</th><th>Recommendation</th></tr>
                </thead>
                <tbody>
                    {assets.map((a) => {
                        const h = getHealth(a);
                        return (
                            <tr key={a.asset_id || a.id || getName(a)}>
                                <td><strong>{getName(a)}</strong><small>{a.asset_type || a.asset_code || ''}</small></td>
                                <td><strong>{getScore(a).toFixed(1)}</strong><small>/100</small></td>
                                <td><Pill value={getStatus(a)} /></td>
                                <td><Pill value={getRisk(a)} /></td>
                                <td>{h.recommendation || h.recommended_action || a.recommendation || 'Monitor equipment'}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function AlertTable({ alerts }) {
    return (
        <div className="maint-table-wrap">
            <table>
                <thead>
                    <tr><th>Equipment</th><th>Alert</th><th>Severity</th><th>Message</th><th>Date</th></tr>
                </thead>
                <tbody>
                    {alerts.map((a, i) => (
                        <tr key={a.id || i}>
                            <td><strong>{a.asset_name || a.asset_code || a.asset_id || '—'}</strong></td>
                            <td>{a.alert_type || a.issue_type || a.type || 'Maintenance alert'}</td>
                            <td><Pill value={a.severity || a.priority || a.risk_level} /></td>
                            <td>{a.message || a.description || a.recommendation || '—'}</td>
                            <td>
                                {a.generated_at
                                    ? new Date(a.generated_at).toLocaleString('en-IN', {
                                        day: '2-digit',
                                        month: 'short',
                                        year: 'numeric',
                                        hour: '2-digit',
                                        minute: '2-digit',
                                    })
                                    : dateText(a.created_at || a.recorded_at || a.alert_date)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function WorkOrderTable({ orders, onStatusChange }) {
    return (
        <div className="maint-table-wrap">
            <table>
                <thead>
                    <tr><th>Work order</th><th>Issue</th><th>Scheduled date</th><th>Priority</th><th>Status</th><th>Update</th></tr>
                </thead>
                <tbody>
                    {orders.map((o) => (
                        <tr key={o.work_order_id}>
                            <td>#{o.work_order_id} · {o.asset_code}</td>
                            <td><strong>{o.issue_type}</strong><small>{o.description || ''}</small></td>
                            <td>{dateText(o.maintenance_date)}</td>
                            <td><Pill value={o.priority} /></td>
                            <td><Pill value={o.status} /></td>
                            <td>
                                <select
                                    value={o.status}
                                    onChange={(e) => onStatusChange(o.work_order_id, e.target.value)}
                                    disabled={['COMPLETED', 'CANCELLED'].includes(o.status)}
                                >
                                    <option value="SCHEDULED">Scheduled</option>
                                    <option value="IN_PROGRESS">In progress</option>
                                    <option value="COMPLETED">Completed</option>
                                    <option value="CANCELLED">Cancelled</option>
                                </select>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

async function askSuggestedQuestion(question) {
    setChatInput(question);

    if (chatLoading) return;

    setChatMessages((prev) => [
        ...prev,
        { role: 'user', content: question },
    ]);

    setChatLoading(true);

    try {
        const result = await maintenance.askMaintenanceAgent(
            facilityId,
            question
        );

        setChatMessages((prev) => [
            ...prev,
            {
                role: 'assistant',
                content: result.answer,
                mode: result.mode,
            },
        ]);
    } catch (error) {
        setChatMessages((prev) => [
            ...prev,
            {
                role: 'assistant',
                content: `Unable to get a response: ${error.message}`,
            },
        ]);
    } finally {
        setChatLoading(false);
    }
}