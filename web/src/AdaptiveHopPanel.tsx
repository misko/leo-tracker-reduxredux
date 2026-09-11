import { useEffect, useState } from "react";
import { getAdaptiveSession, getAdaptiveSessions } from "./adaptive-api";
import type { AdaptiveDetail, AdaptivePage, AdaptiveVisit } from "./adaptive-api";
import { ScannerGlrtPanel } from "./ScannerGlrtPanel";
import { AdaptiveAnalysisPanel } from "./AdaptiveAnalysisPanel";
import { ScannerRefinementPanel } from "./ScannerRefinementPanel";
import "./adaptive-hop.css";

export const targetLabel = (index: number) => `CH${index % 4 + 1}${index < 4 ? "L" : "U"}`;
const seconds = (value: number | null) => value === null ? "Unavailable" : `${value.toFixed(3)} s`;
const duty = (value: number | null) => value === null ? "Unavailable" : `${(value / 10000).toFixed(2)}%`;
const stateAtChoice = (v: AdaptiveVisit, target: number) => v.active_mask & (1 << target)
  ? "active" : v.quiet_mask & (1 << target) ? "quiet" : "unobserved";

export function AdaptiveHopBrowser({ selectedId, onSelect }: {
  selectedId: string | null; onSelect: (id: string) => void;
}) {
  const [cursor, setCursor] = useState(0);
  const [page, setPage] = useState<AdaptivePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true; let busy = false;
    const controller = new AbortController();
    setLoading(true); setPage(null); setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const value = await getAdaptiveSessions(cursor, controller.signal);
        if (active) { setPage(value); setError(null); }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "Adaptive history is unavailable");
      } finally { busy = false; if (active) setLoading(false); }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 30000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [cursor]);
  return <section className="persistent-hop-history adaptive-history" aria-label="Adaptive hop history">
    <header><div><span>ADAPTIVE / SHADOW</span><h3>300-second captures</h3></div>
      <strong>{loading ? "Loading…" : page ? `${page.total} sessions` : "Unavailable"}</strong></header>
    {error ? <p role="status">{error}. Existing scan history remains separate.</p> : null}
    {!loading && !error && page === null ? <p>Adaptive history is not available on this server.</p> : null}
    {page?.total === 0 ? <p>No adaptive or shadow capture has been published yet.</p> : null}
    {page && page.items.length > 0 ? <div className="persistent-hop-scroll"><table className="scanner-history-table" aria-label="Adaptive capture history">
      <thead><tr><th>Capture</th><th>Duty</th></tr></thead>
      <tbody>{page.items.map(c => <tr key={c.session_id} className={selectedId === c.session_id ? "selected" : undefined}>
        <td><button type="button" className="scanner-row-button persistent-hop-row" onClick={() => onSelect(c.session_id)}>
          <time>{new Date(c.captured_at ?? c.recorded_at).toLocaleString()}</time><code>{c.session_id}</code>
          <small>{c.mode} · {c.sample_rate_hz / 1e6} MS/s · {c.retained_visits}/{c.started_visits} visits retained</small>
          <small>{c.captured_at === null ? "RF start unavailable; showing recording creation" : c.utc_qualified ? "Host-bracketed RF start" : "RF UTC estimate unqualified"}</small>
        </button></td><td>{duty(c.valid_duty_ppm)}<small className="persistent-terminal-state">{c.terminal_state}</small></td>
      </tr>)}</tbody>
    </table></div> : null}
    {page && page.total > 5 ? <div className="candidate-pagination scanner-pagination" aria-label="Adaptive history pagination">
      <span>{page.cursor + (page.items.length ? 1 : 0)}–{page.cursor + page.items.length} of {page.total}</span><div>
        <button type="button" disabled={cursor === 0} onClick={() => setCursor(Math.max(0, cursor - 5))}>Previous adaptive captures</button>
        <button type="button" disabled={page.next_cursor === null} onClick={() => page.next_cursor !== null && setCursor(page.next_cursor)}>Next adaptive captures</button>
      </div></div> : null}
  </section>;
}

function Timeline({ detail }: { detail: AdaptiveDetail }) {
  const span = detail.capture.source_span_seconds;
  if (span === null || span === 0) return <p>No attested device-time span is available.</p>;
  const x = (t: number) => 70 + t / span * 900;
  return <svg className="adaptive-timeline" viewBox="0 0 1000 325" role="img" aria-label="Actual retained visits by channel and device time">
    <title>Actual visits; green active, grey quiet, blue unobserved at the hop decision. Outlined marks are incomplete starts.</title>
    {Array.from({ length: 8 }, (_, i) => <g key={i}>
      <text x="5" y={28 + i * 33}>{targetLabel(i)}</text><line x1="70" x2="970" y1={24 + i * 33} y2={24 + i * 33} className="adaptive-grid" />
    </g>)}
    {detail.visits.map(v => v.retained ? <rect key={v.visit_index}
      x={x(v.valid_start_seconds)} y={15 + v.target_index * 33}
      width={(v.valid_end_seconds! - v.valid_start_seconds) / span * 900} height="18"
      className={`adaptive-${stateAtChoice(v, v.target_index)}`}>
      <title>{`Visit ${v.visit_index} · ${targetLabel(v.target_index)} · ${seconds(v.valid_start_seconds)} · ${v.reason}`}</title>
    </rect> : <circle key={v.visit_index} cx={x(v.invalid_start_seconds)} cy={24 + v.target_index * 33} r="3" className="adaptive-incomplete">
      <title>{`Visit ${v.visit_index} started; no complete IQ retained`}</title>
    </circle>)}
    {Array.from({ length: 5 }, (_, i) => <text key={i} x={x(span * i / 4)} y="292" textAnchor="middle">{(span * i / 4).toFixed(1)}</text>)}
    <text x="520" y="317" textAnchor="middle">Device time since capture start (seconds)</text>
  </svg>;
}

export function AdaptiveHopDetail({ sessionId }: { sessionId: string }) {
  const [detail, setDetail] = useState<AdaptiveDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    let active = true; let busy = false;
    const controller = new AbortController();
    setDetail(null); setError(null); setPage(0); setSelected(0);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const value = await getAdaptiveSession(sessionId, controller.signal);
        if (active) { setDetail(value); setError(null); }
      } catch (failure) {
        if (active) { setDetail(null); setError(failure instanceof Error ? failure.message : "Adaptive evidence is unavailable"); }
      } finally { busy = false; }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [sessionId]);
  if (error) return <p className="error-banner" role="alert">{error}</p>;
  if (!detail) return <p role="status">Loading adaptive capture…</p>;
  const c = detail.capture;
  const choice = detail.visits[selected];
  const start = page * 50;
  return <div className="adaptive-detail">
    <header className="recording-heading scanner-heading"><div><p className="section-label">{c.mode.toUpperCase()} HOP CAPTURE</p>
      <h2>Actual channel visits</h2><code>{c.session_id}</code></div><div>{c.terminal_state} · {c.sample_rate_hz / 1e6} MS/s</div></header>
    <dl className="adaptive-summary">
      <div><dt>Source-counter duty</dt><dd>{duty(c.valid_duty_ppm)}</dd></div>
      <div><dt>Attested span / nominal</dt><dd>{seconds(c.source_span_seconds)} / 300 s</dd></div>
      <div><dt>Complete IQ / started hops</dt><dd>{c.retained_visits} / {c.started_visits}</dd></div>
      <div><dt>Capture qualification</dt><dd>{c.capture_qualified ? "Passed recording health gates" : "Not qualified"}</dd></div>
      <div><dt>Fallback choices</dt><dd>{c.fallback_choices}</dd></div>
      <div><dt>Radio / bandwidth</dt><dd>{c.radio_id} / {c.bandwidth_hz / 1e6} MHz</dd></div>
      <div><dt>RF UTC estimate</dt><dd>{c.captured_at === null ? "Unavailable" : new Date(c.captured_at).toLocaleString()} · {c.utc_qualified ? "host-bracket qualified" : "unqualified"}</dd></div>
      <div><dt>UTC bracket width</dt><dd>{c.utc_bracket_width_ms === null ? "Unavailable" : `${c.utc_bracket_width_ms.toFixed(3)} ms`}</dd></div>
    </dl>
    <section className="scanner-results-panel" aria-label="Actual adaptive visit timeline">
      <header><h3>Where the radio actually looked</h3><small>120 ms valid dwell · both receivers retained</small></header>
      <Timeline detail={detail} />
      <p>Green: active · grey: quiet · blue: unobserved at the decision. These are scheduling states, not per-dwell detection verdicts. Outlined marks show the beginning of incomplete hops, not retained IQ.</p>
      {c.mode === "shadow" ? <p>Shadow mode: the radio kept fixed order. Proposals did not change its actual tuning.</p> : null}
      <div className="queue-table-scroll"><table className="queue-table" aria-label="Adaptive channel allocation"><thead><tr>
        <th>Target</th><th>Retained visits</th><th>Valid time</th><th>Allocation</th><th>Max revisit</th><th>Max unobserved</th>
      </tr></thead><tbody>{c.target_coverage.map(row => <tr key={row.target_index}>
        <td>{targetLabel(row.target_index)}</td><td>{row.retained_visits}</td><td>{seconds(row.valid_seconds)}</td>
        <td>{duty(row.allocation_ppm)}</td><td>{seconds(row.maximum_revisit_seconds)}</td><td>{seconds(row.maximum_unobserved_seconds)}</td>
      </tr>)}</tbody></table></div>
      <p>Allocation is a share of retained IQ time, not capture duty. Revisit is start-to-start between complete retained visits; fewer than two visits is unavailable. Unobserved time includes both capture boundaries, without extrapolating beyond this scan.</p>
    </section>
    <section className="scanner-results-panel" aria-label="Adaptive scheduling decisions"><header><h3>Why each hop was chosen</h3></header>
      <p>Three evaluated misses AND two seconds since the latest positive are required for demotion. Unknown breaks the miss streak. Quiet does not prove signal absence.</p>
      {choice ? <div className="adaptive-choice" aria-label="Selected hop decision">
        <strong>Visit {choice.visit_index}: actual {targetLabel(choice.target_index)}; proposed {targetLabel(choice.proposed_target_index)}</strong>
        <p>Proposed-target state: {stateAtChoice(choice, choice.proposed_target_index)} · {choice.consecutive_misses} consecutive misses · {seconds(choice.cooldown_remaining_seconds)} cooldown remaining</p>
        <p>Source feedback basis: {choice.basis_visit === null ? "none" : `visit ${choice.basis_visit}`} · reason: {choice.reason.replaceAll("_", " ")}</p>
        <p>At this choice: {Array.from({ length: 8 }, (_, i) => `${targetLabel(i)} ${stateAtChoice(choice, i)}`).join(" · ")}</p>
        <p>Exact valid start: <code>{choice.valid_start_counter}</code> · decision counter: <code>{choice.decision_counter}</code></p>
      </div> : <p>No hop was started.</p>}
      <div className="queue-table-scroll"><table className="queue-table" aria-label="Adaptive visit decisions"><thead><tr>
        <th>Visit</th><th>Actual / proposed</th><th>Valid boundary</th><th>IQ</th><th>Choice reason</th>
      </tr></thead><tbody>{detail.visits.slice(start, start + 50).map(v => <tr key={v.visit_index}>
        <td><button type="button" aria-pressed={selected === v.visit_index} onClick={() => setSelected(v.visit_index)}>Inspect visit {v.visit_index}</button></td>
        <td>{targetLabel(v.target_index)} / {targetLabel(v.proposed_target_index)}</td><td>{seconds(v.valid_start_seconds)}</td>
        <td>{v.retained ? "120 ms retained" : "Incomplete; not retained"}</td><td>{v.reason.replaceAll("_", " ")}</td>
      </tr>)}</tbody></table></div>
      <p>For an incomplete hop, the valid boundary may not have been reached before cancellation.</p>
      {detail.visits.length > 50 ? <div className="candidate-pagination scanner-pagination">
        <span>{start + 1}–{Math.min(start + 50, detail.visits.length)} of {detail.visits.length}</span><div>
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous visits</button>
          <button type="button" disabled={start + 50 >= detail.visits.length} onClick={() => setPage(page + 1)}>Next visits</button>
        </div></div> : null}
    </section>
    <AdaptiveAnalysisPanel key={`${sessionId}:${c.input_manifest_sha256}`} capture={c} />
    <ScannerRefinementPanel key={`refinement:${sessionId}`} sessionId={sessionId} inputDigest={c.input_manifest_sha256} />
    <ScannerGlrtPanel key={sessionId} sessionId={sessionId} sessionKind="adaptive" />
  </div>;
}
