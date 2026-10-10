import { useEffect, useState, type ReactNode } from "react";

type Point = { channel: number; receiver_id: number; visit: number; time_s: number | null;
  score: number; margin: number; cfo_hz: number | null };
type Channel = { channel: number; receiver_id: number; processed: number; skipped: number;
  active: number; strong: number };
type Report = { run_id: string; recording_name: string; window_count: number;
  session_id?: string;
  counts: { processed: number; skipped_fast_score: number; invalid_capture: number };
  policy: { mode: string; threshold: number; margin_gate: number; strong_margin: number; sample_rate_hz?: number };
  rf_mapping_authorities: string[]; time_basis: string; channels: Channel[]; points?: Point[] };
const colors = ["#2563eb", "#ea580c", "#16a34a", "#dc2626", "#9333ea", "#0d9488", "#db2777", "#64748b"];

async function read<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Fast scan request failed (${response.status})`);
  return response.json() as Promise<T>;
}

type Automatic = { recording_id: string; state: string; edge?: string; failure?: string;
  captured_windows?: number; session_id?: string };

export function FastScanView({ renderTracking, recordingId }: {
  renderTracking?: (sessionId: string) => ReactNode; recordingId?: string;
} = {}) {
  const [items, setItems] = useState<Report[]>([]);
  const [selected, setSelected] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [metric, setMetric] = useState<"cfo" | "score">("cfo");
  const [automatic, setAutomatic] = useState<Automatic[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const [reports, jobs] = await Promise.all([
          read<{ items: Report[] }>("/api/v1/fast-scans?limit=100", controller.signal),
          read<{ items: Automatic[] }>("/api/v1/fast-scans/automatic", controller.signal),
        ]);
        if (!controller.signal.aborted) {
          setItems(reports.items); setAutomatic(jobs.items);
          setSelected(prior => prior || reports.items[0]?.run_id || ""); setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(String(e));
      } finally { busy = false; if (!controller.signal.aborted) setLoading(false); }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  const selectedRun = recordingId ? items.find(item => item.recording_name === recordingId)?.run_id ?? "" : selected;
  const selectedJob = automatic.find(job => job.recording_id === recordingId);
  useEffect(() => {
    setReport(null);
    if (!selectedRun) return;
    const controller = new AbortController();
    setError("");
    read<Report>(`/api/v1/fast-scans/${encodeURIComponent(selectedRun)}`, controller.signal)
      .then(value => { if (!controller.signal.aborted) setReport(value); })
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [selectedRun]);
  const current = report?.run_id === selectedRun ? report : null;
  const trackingId = current?.session_id ?? selectedJob?.session_id;
  const state = selectedJob?.state === "complete" ? "Analysis complete" : selectedJob?.state ?? "Loading capture status…";
  return <section className="adaptive-detail" aria-label="Fast scan detail">
    <header className="recording-heading scanner-heading"><div>
      <p className="section-label">FAST EIGHT-CHANNEL CAPTURE</p>
      <h2>Actual channel visits</h2><code>{recordingId ?? current?.recording_name ?? "Fast scans"}</code>
    </div><div role="status">{state}{selectedJob?.failure && `: ${selectedJob.failure}`}</div></header>
    <dl className="adaptive-summary">
      <div><dt>Complete paired RX visits</dt><dd>{(current?.window_count ?? selectedJob?.captured_windows)?.toLocaleString() ?? "—"}</dd></div>
      <div><dt>Channel coverage</dt><dd>CH1–8 · {selectedJob?.edge ?? "Recorded"} edge</dd></div>
      <div><dt>Retained IQ per receiver</dt><dd>20 ms per visit</dd></div>
      <div><dt>Sample rate</dt><dd>{current?.policy.sample_rate_hz ? `${current.policy.sample_rate_hz / 1e6} MS/s` : "Awaiting published evidence"}</dd></div>
      <div><dt>GLRT evaluated / skipped</dt><dd>{current ? `${current.counts.processed.toLocaleString()} / ${current.counts.skipped_fast_score.toLocaleString()}` : "Awaiting analysis"}</dd></div>
      <div><dt>Invalid capture windows</dt><dd>{current?.counts.invalid_capture.toLocaleString() ?? "Awaiting analysis"}</dd></div>
      <div><dt>RF mapping</dt><dd>{current?.rf_mapping_authorities.join(", ") ?? "Awaiting published evidence"}</dd></div>
    </dl>
    {!recordingId && !!automatic.length && <section className="scanner-results-panel" aria-label="Automatic fast scan processing">
      <h3>Automatic processing</h3>
      <table className="scanner-table"><thead><tr><th>Recording</th><th>Edge</th><th>State</th><th>Captured windows</th></tr></thead>
        <tbody>{automatic.map(job => <tr key={job.recording_id}>
          <td>{job.recording_id}</td><td>{job.edge}</td><td>{job.state}{job.failure && `: ${job.failure}`}</td>
          <td>{job.captured_windows?.toLocaleString()}</td>
        </tr>)}</tbody></table>
    </section>}
    {error && <p className="error-banner" role="alert">{error}</p>}
    <section className="scanner-results-panel adaptive-analysis" aria-label="Fast fractional analysis">
    <header><h3>Fractional GLRT and Doppler analysis</h3><strong>{current ? "Metrics published" : "Awaiting analysis"}</strong></header>
    <p>Automatic analysis uses each selected 20 ms window on both receivers. A skipped window has no GLRT result.</p>
    {loading ? <p>Loading scans…</p> : recordingId && !selectedRun
      ? <p>GLRT results will appear automatically after this capture is sealed and analyzed.</p>
      : !items.length && <p>No completed fast scans published.</p>}
    {!recordingId && !!items.length && <label>Recording <select value={selected} onChange={e => setSelected(e.target.value)}>
      {items.map(r => <option key={r.run_id} value={r.run_id}>{r.recording_name} · {r.policy.mode}</option>)}
    </select></label>}
    {selectedRun && !current && !error && <p>Loading results…</p>}
    {current && <>
      <p>{current.window_count.toLocaleString()} visits: {current.counts.processed.toLocaleString()} processed,
        {" "}{current.counts.skipped_fast_score.toLocaleString()} skipped by fast score,
        {" "}{current.counts.invalid_capture.toLocaleString()} invalid.</p>
      <p>Fast-score cutoff {current.policy.threshold.toFixed(5)}. Candidate detections feed the shared trajectory, catalogue and positioning artifacts below.</p>
    </>}
    </section>
    {trackingId ? renderTracking?.(trackingId) : <section className="scanner-artifact-panel" aria-label="Shared analysis publication">
      <header><div><span>TRAJECTORY AND CATALOGUE EVIDENCE</span><h3>Tracking and positioning</h3></div></header>
      <p>Shared analysis artifacts will appear automatically after GLRT publishes its tracking input.</p>
    </section>}
    {current && <details className="scanner-results-panel fast-diagnostics">
      <summary>Fast-score diagnostics and channel activity</summary>
      <p>Time: {current.time_basis}. These supplemental plots show the strongest saved candidate per window.</p>
      <label>Plot <select value={metric} onChange={e => setMetric(e.target.value as "cfo" | "score")}>
        <option value="cfo">Time vs CFO — strong GLRT only</option>
        <option value="score">Fast score vs GLRT margin — processed windows</option>
      </select></label>
      <p>{colors.map((color, i) => <span key={i} style={{ color, marginRight: 18 }}>● CH{i + 1}</span>)}</p>
      {[...new Set(current.channels.map(c => c.receiver_id))].map(rx =>
        <Scatter key={rx} receiver={rx} metric={metric} report={current} />)}
      <h3>Candidate activity by channel and receiver</h3>
      <p>Active: margin ≥ {current.policy.margin_gate}; strong: margin ≥ {current.policy.strong_margin}.
        Counts are windows, not satellites.</p>
      <table className="scanner-table"><thead><tr>
        {["Channel", "Receiver", "Processed", "Skipped", "Active", "Strong"].map(s => <th key={s}>{s}</th>)}
      </tr></thead><tbody>{current.channels.map(c => <tr key={`${c.channel}-${c.receiver_id}`}>
        <td>CH{c.channel}</td><td>RX{c.receiver_id + 1}</td><td>{c.processed}</td><td>{c.skipped}</td>
        <td>{c.active}</td><td>{c.strong}</td></tr>)}</tbody></table>
    </details>}
  </section>;
}

function Scatter({ receiver, metric, report }: { receiver: number; metric: "cfo" | "score"; report: Report }) {
  const points = (report.points ?? []).filter(p => p.receiver_id === receiver &&
    (metric === "score" || (p.margin >= report.policy.strong_margin && p.time_s !== null && p.cfo_hz !== null)));
  const coordinates = points.map(p => ({ p, x: metric === "cfo" ? p.time_s! : p.score,
    y: metric === "cfo" ? p.cfo_hz! / 1000 : p.margin }));
  const xs = coordinates.map(v => v.x), ys = coordinates.map(v => v.y);
  const xmin = xs.reduce((a, b) => Math.min(a, b), 0);
  const xmax = xs.reduce((a, b) => Math.max(a, b), xmin + 0.001);
  const ymin = ys.reduce((a, b) => Math.min(a, b), 0);
  const ymax = ys.reduce((a, b) => Math.max(a, b), ymin + 0.001);
  const x = (value: number) => 75 + 900 * (value - xmin) / (xmax - xmin);
  const y = (value: number) => 250 - 225 * (value - ymin) / (ymax - ymin);
  return <section><h3>RX{receiver + 1} · {points.length.toLocaleString()} windows</h3>
    {!points.length ? <p>No qualifying points.</p> : <svg viewBox="0 0 1020 300" role="img"
      aria-label={`RX${receiver + 1} ${metric === "cfo" ? "CFO over time" : "fast score versus GLRT margin"}`}
      style={{ width: "100%", background: "white", border: "1px solid #cbd5e1" }}>
      <path d="M75 20V250H985" fill="none" stroke="#64748b" />
      {[0, .25, .5, .75, 1].map(t => <g key={t} fill="#334155" fontSize="12">
        <text x={x(xmin + t * (xmax - xmin))} y="268" textAnchor="middle">{(xmin + t * (xmax - xmin)).toFixed(metric === "cfo" ? 1 : 3)}</text>
        <text x="68" y={y(ymin + t * (ymax - ymin)) + 4} textAnchor="end">{(ymin + t * (ymax - ymin)).toFixed(3)}</text>
      </g>)}
      <text x="520" y="291" textAnchor="middle" fill="#334155">{metric === "cfo" ? "Relative sample time (s)" : "Fast score"}</text>
      <text x="16" y="140" transform="rotate(-90 16 140)" textAnchor="middle" fill="#334155">{metric === "cfo" ? "CFO (kHz)" : "GLRT margin"}</text>
      {coordinates.map(({ p, x: px, y: py }) => <circle key={p.visit} cx={x(px)} cy={y(py)} r="1.8"
        fill={colors[p.channel - 1]} opacity="0.65"><title>CH{p.channel}, visit {p.visit}: score {p.score.toFixed(5)}, margin {p.margin.toFixed(5)}, CFO {p.cfo_hz?.toFixed(1)} Hz</title></circle>)}
    </svg>}
  </section>;
}
