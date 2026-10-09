import { useEffect, useState } from "react";
import { getAdaptiveSessions } from "./adaptive-api";
import { verify, type Status } from "./RegionalPosition";
import "./position-error.css";

export type ErrorPoint = { sessionId: string; time: number; fitted: number | null; zero: number | null };
type Result = { points: ErrorPoint[]; scans: number; unavailable: number; failed: number; truncated: boolean };
const colors = { fitted: "#137ab2", zero: "#b65415" };
const arms = ["fitted", "zero"] as const;
const names = { fitted: "Fitted c", zero: "c = 0" };

export function logDomain(values: number[]): [number, number] {
  const positive = values.filter(value => Number.isFinite(value) && value > 0);
  if (!positive.length) return [-3, 0];
  const low = Math.floor(Math.log10(Math.min(...positive)));
  return [low, Math.max(low + 1, Math.ceil(Math.log10(Math.max(...positive))))];
}

export function histogram(values: number[], domain: [number, number], bins = 12) {
  const counts = Array<number>(bins).fill(0);
  const [low, high] = domain;
  for (const value of values) {
    if (!Number.isFinite(value) || value <= 0) continue;
    const index = Math.floor((Math.log10(value) - low) / (high - low) * bins);
    counts[Math.max(0, Math.min(bins - 1, index))]++;
  }
  return counts;
}

export async function loadErrors(start: number, end: number, version: number, signal: AbortSignal,
  progress: (count: number) => void): Promise<Result> {
  const result: Result = { points: [], scans: 0, unavailable: 0, failed: 0, truncated: false };
  const seen = new Set<string>();
  let cursor = 0;
  // Bounded history traversal; report partial coverage explicitly at the cap.
  for (let pageNumber = 0; pageNumber < 200; pageNumber++) {
    signal.throwIfAborted();
    const page = await getAdaptiveSessions(cursor, signal);
    if (!page) throw new Error("Adaptive scan history is unavailable.");
    const captures = page.items.filter(capture => {
      if (seen.has(capture.session_id)) return false;
      seen.add(capture.session_id);
      const time = Date.parse(capture.captured_at ?? capture.recorded_at);
      return time >= start && time <= end;
    });
    // Four requests at a time keep the read-only browser workload bounded.
    for (let offset = 0; offset < captures.length; offset += 4) {
      await Promise.all(captures.slice(offset, offset + 4).map(async capture => {
        result.scans++;
        try {
          const response = await fetch(`/api/v1/scanner/tracking/${encodeURIComponent(capture.session_id)}/regional-position-v${version}`, { signal });
          if (response.status === 404) { result.unavailable++; return; }
          if (!response.ok) throw new Error(`Position request failed (${response.status})`);
          const status = await response.json() as Status;
          verify(status, capture.session_id, capture.input_manifest_sha256, version);
          const method = status.manifest?.document.methods.find(m => m.name === "V16");
          const value = (name: string) => {
            const selected = method?.arms.find(a => a.name === name)?.selected;
            if (!selected) return null;
            const error = selected.horizontal_error_m;
            if (!Number.isFinite(error) || error < 0) throw new Error("Invalid position error");
            return error / 1000;
          };
          const fitted = value("fitted-c"), zero = value("zero-c");
          if (fitted === null && zero === null) result.unavailable++;
          else result.points.push({ sessionId: capture.session_id,
            time: Date.parse(capture.captured_at ?? capture.recorded_at), fitted, zero });
        } catch (error) {
          if (signal.aborted) throw error;
          result.failed++;
        }
      }));
    }
    progress(seen.size);
    if (page.next_cursor === null) break;
    // History is newest-first by capture time. Once a whole page precedes the
    // requested range, later pages cannot contribute any plotted scans.
    if (page.items.length > 0 && page.items.every(capture =>
      Date.parse(capture.captured_at ?? capture.recorded_at) < start)) break;
    cursor = page.next_cursor;
    if (pageNumber === 199) result.truncated = true;
  }
  result.points.sort((a, b) => a.time - b.time);
  return result;
}

function localInput(time: number) {
  const date = new Date(time);
  return new Date(time - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function PositionErrorPanel() {
  const [start, setStart] = useState(() => localInput(Date.now() - 86400000));
  const [end, setEnd] = useState(() => localInput(Date.now()));
  const [version, setVersion] = useState(3);
  const [request, setRequest] = useState(() => ({ start: Date.now() - 86400000, end: Date.now(), version: 3 }));
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setResult(null); setError(null); setProgress(0);
    loadErrors(request.start, request.end, request.version, controller.signal, setProgress)
      .then(value => { if (!controller.signal.aborted) setResult(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(String(reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request]);
  const points = result?.points ?? [];
  const maximum = Math.max(1, ...points.flatMap(p => [p.fitted ?? 0, p.zero ?? 0]));
  const domain = logDomain(points.flatMap(p => [p.fitted ?? 0, p.zero ?? 0]));
  const [logMin, logMax] = domain;
  const tickStep = Math.max(1, Math.ceil((logMax - logMin) / 6));
  const ticks = Array.from({ length: Math.floor((logMax - logMin) / tickStep) + 1 }, (_, i) => logMin + i * tickStep);
  if (ticks.at(-1) !== logMax) ticks.push(logMax);
  const distributions = arms.map(arm => histogram(points.flatMap(p => p[arm] === null ? [] : [p[arm]!]), domain));
  const maxCount = Math.max(1, ...distributions.flat());
  const y = (v: number) => 270 - v / maximum * 230;
  const x = (t: number) => 70 + (t - request.start) / (request.end - request.start) * 690;
  return <section className="position-errors" aria-label="Adaptive scans position error">
    <h2>Adaptive scans position error</h2>
    <p>Horizontal distance to the saved receiver reference, in km. These are diagnostic estimates; the reference is not surveyed ground truth.</p>
    <form onSubmit={event => {
      event.preventDefault();
      const a = Date.parse(start), b = Date.parse(end);
      if (!Number.isFinite(a) || !Number.isFinite(b) || a >= b) { setError("Choose an end time after the start time."); return; }
      setRequest({ start: a, end: b, version });
    }}>
      <label>From <input type="datetime-local" value={start} required onChange={e => setStart(e.target.value)} /></label>
      <label>To <input type="datetime-local" value={end} required onChange={e => setEnd(e.target.value)} /></label>
      <label>Position method <select value={version} onChange={e => setVersion(Number(e.target.value))}>
        <option value={3}>Hard60 B7 (v3)</option><option value={2}>Hard60 (v2)</option><option value={1}>Historical V16 (v1)</option>
      </select></label>
      <button type="submit">Update plots</button>
      {[6, 24, 72, 168].map(hours => <button type="button" key={hours} onClick={() => {
        const b = Date.now(), a = b - hours * 3600000;
        setStart(localInput(a)); setEnd(localInput(b)); setRequest({ start: a, end: b, version });
      }}>Last {hours === 168 ? "7 days" : `${hours} hours`}</button>)}
    </form>
    <p>Times use {Intl.DateTimeFormat().resolvedOptions().timeZone}. Each point is one scan. Both plots use the same range and method.</p>
    {loading && <p role="status">Loading saved results… {progress} history records checked.</p>}
    {error && <p role="alert">{error}</p>}
    {result && <>
      <p>{result.scans} scans in range · {points.length} with estimates · {result.unavailable} unavailable · {result.failed} requests or verification checks failed.</p>
      {result.truncated && <p role="alert">Partial coverage: the 2,000-record history limit was reached. Older scans may be missing.</p>}
      {result.failed > 0 && <p role="alert">Some results could not be loaded or verified. Update plots to retry.</p>}
      {!points.length ? <p>No position estimates for this time range and method.</p> : <>
        <p className="error-legend">{arms.map(arm => <span key={arm} style={{ color: colors[arm] }}>{names[arm]}: {points.filter(p => p[arm] !== null).length} estimates</span>)}</p>
        <h3>Position error over time</h3>
        <svg viewBox="0 0 800 330" role="img" aria-label="Capture time versus horizontal position error in kilometres">
          {[0, .25, .5, .75, 1].map(f => <g key={f}><line x1="70" x2="760" y1={y(f * maximum)} y2={y(f * maximum)} stroke="#b6c4ce" /><text x="60" y={y(f * maximum) + 4} textAnchor="end">{(f * maximum).toFixed(1)}</text></g>)}
          <text x="15" y="20">Error (km)</text>
          {[0, .5, 1].map(f => <text key={f} x={70 + 690 * f} y="295" textAnchor={f === 0 ? "start" : f === 1 ? "end" : "middle"}>{new Date(request.start + (request.end - request.start) * f).toLocaleString()}</text>)}
          {points.flatMap(p => arms.map(arm => p[arm] !== null && <circle key={`${p.sessionId}-${arm}`} cx={x(p.time)} cy={y(p[arm]!)} r={arm === "fitted" ? 4 : 2.5} fill={colors[arm]} opacity="0.8"><title>{p.sessionId} · {new Date(p.time).toLocaleString()} · {names[arm]}: {p[arm]!.toFixed(3)} km</title></circle>))}
        </svg>
        <h3>Position error histogram</h3>
        <p>Logarithmic error axis (km). Zero-error estimates are excluded from the histogram: fitted c {points.filter(p => p.fitted === 0).length}, c = 0 {points.filter(p => p.zero === 0).length}. They remain in the time plot and table.</p>
        <svg viewBox="0 0 800 330" role="img" aria-label="Histogram of horizontal position errors in kilometres on a base-10 logarithmic axis">
          <text x="15" y="20">Scans</text>
          {[0, .5, 1].map(f => <g key={f}><line x1="70" x2="760" y1={270 - 230 * f} y2={270 - 230 * f} stroke="#b6c4ce"/><text x="60" y={274 - 230 * f} textAnchor="end">{(maxCount * f).toFixed(0)}</text></g>)}
          {arms.flatMap((arm, a) => distributions[a].map((count, i) => <rect key={`${arm}-${i}`} x={70 + i * 57.5 + a * 26} y={270 - count / maxCount * 230} width="24" height={count / maxCount * 230} fill={colors[arm]}><title>{names[arm]} · {(10 ** (logMin + i * (logMax - logMin) / 12)).toPrecision(3)}–{(10 ** (logMin + (i + 1) * (logMax - logMin) / 12)).toPrecision(3)} km: {count} scans</title></rect>))}
          {ticks.map(exponent => <text key={exponent} x={70 + 690 * (exponent - logMin) / (logMax - logMin)} y="295" textAnchor="middle">10<tspan baselineShift="super" fontSize="9">{exponent}</tspan></text>)}
          <text x="415" y="322" textAnchor="middle">Horizontal position error (km, log scale)</text>
        </svg>
        <details><summary>View plotted values</summary><table><thead><tr><th>Capture time</th><th>Scan</th><th>Fitted c (km)</th><th>c = 0 (km)</th></tr></thead><tbody>{points.map(p => <tr key={p.sessionId}><td>{new Date(p.time).toLocaleString()}</td><td><a href={`?scan_id=${encodeURIComponent(p.sessionId)}`}>{p.sessionId}</a></td><td>{p.fitted?.toFixed(3) ?? "Unavailable"}</td><td>{p.zero?.toFixed(3) ?? "Unavailable"}</td></tr>)}</tbody></table></details>
      </>}
    </>}
  </section>;
}
