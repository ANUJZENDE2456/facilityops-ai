import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import * as api from './services/energyService';
import './App.css';
import MaintenanceDashboard from './components/maintenanceDashboard.jsx';

const TABS = ['Campus Overview', 'Building Detail', 'Anomalies', 'AI Energy Agent', 'Recommendations'];
const METERS = ['MAIN-METER-01', 'HVAC-01', 'LIGHTING-01', 'PLUG-LOAD-01'];
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const ENGINES = { gemini: 'Gemini', claude: 'Claude', ollama: 'Local model', rules: 'Rule-based fallback' };
const CHIPS = ['Why are there anomalies?', 'How can we save energy?', 'What is the cost?', 'Which meter uses the most energy?'];
const num = (n, d = 0) => Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
const inr = (n) => '\u20B9' + num(n);
const when = (t) => new Date(t).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
const tip = {
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  color: '#172033',
  padding: '10px'
};

function useLoad(fn, deps) {
  const [s, set] = useState({ data: null, error: '', loading: true });
  useEffect(() => {
    let live = true;
    set((p) => ({ ...p, loading: true, error: '' }));
    fn().then((d) => live && set({ data: d, error: '', loading: false }))
      .catch((e) => live && set({ data: null, error: e.message, loading: false }));
    return () => { live = false; };
  }, deps);
  return s;
}

function Status({ s, msg }) {
  if (s.error) return <div className="status err">Could not load data: {s.error}</div>;
  if (s.loading) return <div className="status">{msg || 'Loading...'}</div>;
  return null;
}

function Kpi({ label, value, sub, tone = '' }) {
  return <div className={`kpi ${tone}`}><span>{label}</span><strong>{value}</strong>{sub && <small>{sub}</small>}</div>;
}

function Heatmap({ data }) {
  const cell = {};
  data.forEach((d) => (cell[`${d.weekday}-${d.hour}`] = d.power_kw));
  const vals = data.map((d) => d.power_kw);
  const min = Math.min(...vals), max = Math.max(...vals);
  return (
    <div className="heatmap">
      <div className="hm-row hm-head"><span />{Array.from({ length: 24 }, (_, h) => <span key={h}>{h % 3 === 0 ? h : ''}</span>)}</div>
      {WEEKDAYS.map((day, w) => (
        <div className="hm-row" key={day}>
          <span className="hm-label">{day}</span>
          {Array.from({ length: 24 }, (_, h) => {
            const v = cell[`${w}-${h}`];
            const a = v === undefined ? 0 : 0.12 + 0.88 * ((v - min) / (max - min || 1));
            return <span key={h} className="hm-cell" title={`${day} ${h}:00 - ${v ?? '-'} kW`} style={{ background: `rgba(56,189,248,${a})` }} />;
          })}
        </div>
      ))}
    </div>
  );
}

function CampusOverview({ onOpen }) {
  const s = useLoad(() => api.getCampus(), []);
  if (!s.data) return <Status s={s} msg="Analysing all buildings with the ML detectors (first load takes a few seconds)..." />;
  const { buildings, totals } = s.data;
  return (
    <>
      <section className="kpis">
        <Kpi label="Monitored buildings" value={totals.buildings} />
        <Kpi label="Campus energy (30 days)" value={`${num(totals.energy_kwh)} kWh`} />
        <Kpi label="Estimated cost" value={inr(totals.cost_inr)} />
        <Kpi label="Incidents (7 days)" value={totals.incidents_7d} sub={`${totals.anomalies_7d} flagged readings`} tone="rose" />
      </section>
      <div className="two">
        <section className="panel">
          <h2>Energy by building (30 days)</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={buildings}>
              <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} />
              <YAxis stroke="#94a3b8" fontSize={12} width={70} />
              <Tooltip contentStyle={tip} formatter={(v) => `${num(v)} kWh`} />
              <Bar dataKey="energy_kwh" fill="#38bdf8" radius={[4, 4, 0, 0]} name="Energy" />
            </BarChart>
          </ResponsiveContainer>
        </section>
        <section className="panel">
          <h2>Incidents by building (7 days)</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={buildings}>
              <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} />
              <YAxis stroke="#94a3b8" fontSize={12} width={40} allowDecimals={false} />
              <Tooltip contentStyle={tip} />
              <Bar dataKey="incidents_7d" fill="#f43f5e" radius={[4, 4, 0, 0]} name="Incidents" />
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>
      <section className="panel">
        <h2>Building comparison</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Building</th><th>Type</th><th>Energy</th><th>Cost</th><th>Peak</th><th>Incidents</th><th>Flagged readings</th><th>Critical / High</th><th /></tr></thead>
            <tbody>
              {buildings.map((b) => (
                <tr key={b.facility_id}>
                  <td>{b.name}</td><td>{b.building_type}</td><td>{num(b.energy_kwh)} kWh</td><td>{inr(b.cost_inr)}</td>
                  <td>{num(b.peak_power_kw, 1)} kW</td><td>{b.incidents_7d}</td><td>{b.anomalies_7d}</td><td>{b.critical_7d} / {b.high_7d}</td>
                  <td><button className="link" onClick={() => onOpen(b.facility_id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function BuildingDetail({ fid }) {
  const [days, setDays] = useState(30);
  const [hours, setHours] = useState(168);
  const [meter, setMeter] = useState(METERS[0]);
  const sum = useLoad(() => api.getSummary(fid, days), [fid, days]);
  const ts = useLoad(() => api.getTimeseries(fid, meter, hours), [fid, meter, hours]);
  if (!sum.data) return <Status s={sum} />;
  const k = sum.data.kpis;
  return (
    <>
      <div className="toolbar">
        <label>Period<select value={days} onChange={(e) => setDays(+e.target.value)}>{[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select></label>
      </div>
      <section className="kpis">
        <Kpi label="Total energy" value={`${num(k.total_energy_kwh)} kWh`} />
        <Kpi label="Estimated cost" value={inr(k.cost_inr)} />
        <Kpi label="Carbon footprint" value={`${k.carbon_tco2e} tCO2e`} />
        <Kpi label="Peak power" value={`${num(k.peak_power_kw, 1)} kW`} />
        <Kpi label="Average power" value={`${num(k.average_power_kw, 1)} kW`} />
        <Kpi label="Off-hours share" value={`${k.off_hours_share_pct}%`} sub="before 7:00, after 20:00, weekends" tone="amber" />
      </section>
      <section className="panel">
        <div className="panel-head">
          <h2>Power trend</h2>
          <div className="controls">
            <select value={meter} onChange={(e) => setMeter(e.target.value)}>{METERS.map((m) => <option key={m}>{m}</option>)}</select>
            <select value={hours} onChange={(e) => setHours(+e.target.value)}>{[[24, '24 hours'], [72, '3 days'], [168, '7 days'], [336, '14 days']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </div>
        </div>
        {ts.data ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={ts.data.points}>
              <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" tickFormatter={when} minTickGap={50} stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} unit=" kW" width={70} />
              <Tooltip labelFormatter={when} contentStyle={tip} />
              <Line type="monotone" dataKey="power_kw" stroke="#38bdf8" dot={false} strokeWidth={2} name="Power (kW)" />
            </LineChart>
          </ResponsiveContainer>
        ) : <Status s={ts} />}
      </section>
      <div className="two">
        <section className="panel">
          <h2>Energy by meter</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={sum.data.meter_breakdown}>
              <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
              <XAxis dataKey="meter_id" stroke="#94a3b8" fontSize={11} />
              <YAxis stroke="#94a3b8" fontSize={12} width={70} />
              <Tooltip contentStyle={tip} formatter={(v) => `${num(v)} kWh`} />
              <Bar dataKey="energy_kwh" fill="#14b8a6" radius={[4, 4, 0, 0]} name="Energy" />
            </BarChart>
          </ResponsiveContainer>
        </section>
        <section className="panel">
          <h2>Average load by weekday and hour</h2>
          <Heatmap data={sum.data.heatmap} />
          <small className="hint">Brighter = higher power. Glow at night or on weekends means wasted energy.</small>
        </section>
      </div>
    </>
  );
}

function Anomalies({ fid }) {
  const s = useLoad(() => api.getAnomalies(fid, 168), [fid]);
  if (!s.data) return <Status s={s} msg="Running anomaly detection..." />;
  const a = s.data.anomaly_summary;
  return (
    <>
      <section className="kpis">
        <Kpi label="Incidents (7 days)" value={s.data.incidents.length} sub="consecutive flagged hours grouped" tone="rose" />
        <Kpi label="Flagged readings" value={a.total} />
        <Kpi label="Critical / High" value={`${a.critical} / ${a.high}`} tone="amber" />
        <Kpi label="Medium / Low" value={`${a.medium} / ${a.low}`} />
      </section>
      <section className="panel">
        <h2>Incidents (grouped events)</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Meter</th><th>Started</th><th>Duration</th><th>Peak power</th><th>Readings</th><th>Severity</th></tr></thead>
            <tbody>
              {s.data.incidents.slice(0, 40).map((x, i) => (
                <tr key={i}><td>{x.meter_id}</td><td>{when(x.start)}</td><td>{x.duration_h} h</td><td>{num(x.peak_power_kw, 1)} kW</td><td>{x.readings}</td><td><span className={`badge ${x.severity}`}>{x.severity}</span></td></tr>
              ))}
            </tbody>
          </table>
          {s.data.incidents.length === 0 && <p className="hint">No incidents detected.</p>}
        </div>
      </section>
      <section className="panel">
        <h2>Flagged readings (highest scores)</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Meter</th><th>Time</th><th>Power</th><th>Score</th><th>Severity</th></tr></thead>
            <tbody>
              {s.data.anomalies.slice(0, 40).map((x, i) => (
                <tr key={i}><td>{x.meter_id}</td><td>{when(x.recorded_at)}</td><td>{num(x.power_kw, 1)} kW</td><td>{x.anomaly_score.toFixed(2)}</td><td><span className={`badge ${x.severity}`}>{x.severity}</span></td></tr>
              ))}
            </tbody>
          </table>
          {s.data.anomalies.length === 0 && <p className="hint">No anomalies detected.</p>}
        </div>
      </section>
    </>
  );
}

function rich(text) {
  return text.split('\n').map((line, i) => {
    const bullet = /^\s*[*-]\s+/.test(line);
    const parts = line.replace(/^\s*[*-]\s+/, '').split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2, -2)}</strong> : p);
    return <div key={i} className={bullet ? 'li' : ''}>{bullet ? '\u2022 ' : ''}{parts}</div>;
  });
}

function Agent({ fid, name }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => setMsgs([]), [fid]);

  async function send(text) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setQ('');
    setMsgs((m) => [...m, { role: 'user', text: question }]);
    setBusy(true);
    try {
      const r = await api.askAgent(fid, question);
      setMsgs((m) => [...m, { role: 'agent', text: r.answer, mode: r.mode, ms: r.total_ms, llm: r.llm_ms, note: r.note }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: 'agent', text: `Sorry, the agent could not answer: ${e.message}`, mode: 'rules' }]);
    }
    setBusy(false);
  }

  return (
    <section className="panel chat">
      <h2>AI Energy Agent <small className="hint">- {name}</small></h2>
      <p className="hint">The agent runs the ML anomaly detectors and analytics, then an LLM explains the results. It answers only from this building's data.</p>
      <div className="chips">{CHIPS.map((c) => <button key={c} className="chip" disabled={busy} onClick={() => send(c)}>{c}</button>)}</div>
      <div className="msgs">
        {msgs.length === 0 && <p className="hint">Ask a question or tap a suggestion.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.role === 'agent' ? rich(m.text) : m.text}</div>
            {m.role === 'agent' && m.mode && <small className="hint">Answered by {ENGINES[m.mode] || m.mode}{m.ms ? ` in ${(m.ms / 1000).toFixed(1)}s` : ''}{m.llm ? ` (AI model ${(m.llm / 1000).toFixed(1)}s, data analysis ${((m.ms - m.llm) / 1000).toFixed(1)}s)` : ''}</small>}
          </div>
        ))}
        {busy && <div className="msg agent"><div className="bubble">Analysing...</div></div>}
      </div>
      <div className="ask-row">
        <input value={q} placeholder="e.g. Why did HVAC spike at night?" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} />
        <button onClick={() => send()} disabled={busy}>Ask</button>
      </div>
    </section>
  );
}

function Recommendations({ fid }) {
  const s = useLoad(() => api.getAnomalies(fid, 168), [fid]);
  if (!s.data) return <Status s={s} />;
  return (
    <section className="panel">
      <h2>Recommendations</h2>
      {s.data.recommendations.map((r, i) => (
        <div className="rec" key={i}>
          <div><strong>{r.title}</strong><span className={`badge ${r.priority}`}>{r.priority}</span></div>
          <small>{r.category}</small>
          <p>{r.description}</p>
        </div>
      ))}
    </section>
  );
}

export default function App() {
  const [tab, setTab] = useState(TABS[0]);
  const [module, setModule] = useState('Energy');
  const [facilities, setFacilities] = useState([]);
  const [fid, setFid] = useState(null);
  const [error, setError] = useState('');


  useEffect(() => {
    api.getFacilities().then((f) => { setFacilities(f); if (f.length) setFid(f[0].id); }).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="state"><h2>Unable to reach the backend</h2><p>{error}</p><button onClick={() => location.reload()}>Retry</button></div>;
  if (!fid) return <div className="state">Loading FacilityOps AI...</div>;
  const current = facilities.find((f) => f.id === fid);
  const open = (id) => { setFid(id); setTab('Building Detail'); };

  return (
    <div className="app">
      <header>
        <div>
          <h1>FacilityOps AI <span>Energy Intelligence &amp; Monitoring</span></h1>
          <p>Agentic FacilityOps AI Platform | Simulated campus data</p>
        </div>
        <label>Building
          <select value={fid} onChange={(e) => setFid(+e.target.value)}>
            {facilities.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
      </header>
      <nav className="module-nav">
        <button
          className={module === 'Energy' ? 'active' : ''}
          onClick={() => setModule('Energy')}
        >
          Energy Monitoring
        </button>
        <button
          className={module === 'Maintenance' ? 'active' : ''}
          onClick={() => setModule('Maintenance')}
        >
          Predictive Maintenance
        </button>
      </nav>

      {module === 'Energy' && (
        <nav>
          {TABS.map((t) => (
            <button
              key={t}
              className={t === tab ? 'active' : ''}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>
      )}
      {module === 'Energy' ? (
        <>
          {tab === 'Campus Overview' && <CampusOverview onOpen={open} />}
          {tab === 'Building Detail' && <BuildingDetail fid={fid} />}
          {tab === 'Anomalies' && <Anomalies fid={fid} />}
          {tab === 'AI Energy Agent' && <Agent fid={fid} name={current?.name} />}
          {tab === 'Recommendations' && <Recommendations fid={fid} />}
        </>
      ) : (
        <MaintenanceDashboard facilityId={fid} />
      )}
    </div>
  );
}
