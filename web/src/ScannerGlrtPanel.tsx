import { useEffect, useState } from "react";
import { getScannerGlrt } from "./api";
import type { ScannerGlrtPublicationV1, ScannerGlrtResultV1 } from "./api";

const PAGE_SIZE = 50;

function confirmationMs(row: ScannerGlrtResultV1): string {
  // Subtract exact uint64 anchors BEFORE converting the small interval.
  const samples = BigInt(row.confirmation_end) - BigInt(row.confirmation_start);
  return (Number(samples) * 1000 / row.rate_hz).toFixed(1);
}

export function ScannerGlrtPanel({ sessionId }: { sessionId: string }) {
  const [publication, setPublication] = useState<ScannerGlrtPublicationV1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let busy = false;
    setPublication(null);
    setLoading(true);
    setError(null);
    setPage(0);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const value = await getScannerGlrt(sessionId, controller.signal);
        if (active) { setPublication(value); setError(null); }
      } catch (failure) {
        if (active && !controller.signal.aborted) {
          setPublication(null);
          setError(failure instanceof Error ? failure.message : "GLRT evidence is unavailable");
        }
      } finally {
        busy = false;
        if (active) setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15_000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [sessionId]);
  const evidence = publication?.evidence;
  const rows = evidence?.results ?? [];
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1));
  const start = currentPage * PAGE_SIZE;
  const failure = error ?? publication?.error ?? evidence?.error;
  const unqualified = evidence?.mode === "unqualified-evidence";
  return <section className="scanner-results-panel scanner-glrt-panel" aria-label="On-radio GLRT">
    <header><div><span>RADIO-SIDE RESULTS</span><h3>On-radio GLRT · RX1</h3></div>
      <small>Independent of desktop re-analysis</small></header>
    {loading ? <p role="status">Loading radio-side GLRT evidence…</p> : null}
    {failure ? <p role="status">GLRT evidence unavailable: {failure}. This is not a no-signal result.</p> : null}
    {!loading && !failure && publication === null ? <p>No on-radio GLRT evidence was recorded for this capture. Signal presence is unknown.</p> : null}
    {evidence ? <>
      <p>{unqualified ? <strong>Unqualified measurements — not Starlink classifications.</strong> : "Radio classifier evidence."}</p>
      <p>{rows.length}/{evidence.expected_results ?? "unknown"} results delivered · {evidence.delivery_complete ? "delivery complete" : "delivery incomplete"}
        {" · "}{evidence.classification_complete ? "classification complete" : "classification incomplete"}
        {" · "}{evidence.dropped_results} reported dropped results</p>
      <p>Screen coverage is not confirmation coverage and does not establish absence. Radio compute times are not measured scanner duty.</p>
      <details><summary>Artifact identity and source binding</summary>
        <p>Session: <code>{sessionId}</code></p>
        <p>Capture: <code>{publication?.input_manifest_sha256}</code></p>
        <p>Algorithm: <code>{publication?.algorithm_sha256}</code></p>
        <p>Configuration: <code>{publication?.configuration_sha256}</code></p>
      </details>
      {rows.length ? <>
        <div className="queue-table-scroll scanner-results-scroll"><table className="queue-table scanner-table" aria-label="Radio-side GLRT dwell results">
          <thead><tr><th>Visit / channel</th><th>Verdict</th><th>Exact / margin</th><th>CFO</th><th>Coverage</th><th>Compute CPU / wall</th><th>Exact epoch</th></tr></thead>
          <tbody>{rows.slice(start, start + PAGE_SIZE).map((row) => {
            const confirmed = row.confirmation_end !== row.confirmation_start;
            const coverage = row.search_window_mask.toString(2).replaceAll("0", "").length;
            return <tr key={row.sequence}>
              <td>{row.visit} · CH{row.channel}{row.edge === "lower" ? "L" : "U"}</td>
              <td>{row.verdict === "starlink" ? "Starlink" : row.verdict === "no_signal" ? "No signal" : `Unavailable: ${row.reason.replaceAll("_", " ")}`}</td>
              <td>{confirmed ? `${row.exact_score.toFixed(4)} / ${row.margin.toFixed(4)}` : "—"}</td>
              <td>{confirmed ? `${(row.cfo_hz / 1000).toFixed(3)} kHz` : "—"}</td>
              <td>Screen {coverage}/6 · confirm {confirmationMs(row)} ms</td>
              <td>{row.cpu_ms.toFixed(1)} / {row.wall_ms.toFixed(1)} ms</td>
              <td>{confirmed ? <><code>{row.epoch_sample_counter}</code><br />{row.fractional_offset_samples >= 0 ? "+" : ""}{row.fractional_offset_samples.toFixed(4)} samples</> : "—"}</td>
            </tr>;
          })}</tbody>
        </table></div>
        <div className="candidate-pagination scanner-pagination" aria-label="GLRT result pagination">
          <span>Showing {start + 1}–{Math.min(start + PAGE_SIZE, rows.length)} of {rows.length}</span>
          <div><button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous GLRT results</button>
            <button type="button" disabled={start + PAGE_SIZE >= rows.length} onClick={() => setPage(currentPage + 1)}>Next GLRT results</button></div>
        </div>
      </> : null}
    </> : null}
  </section>;
}
