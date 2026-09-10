import { useEffect, useState } from "react";
import { getNativeRecording, getNativeRecordings } from "./nativeRecordingsApi";
import type { NativeRecordingDetail, NativeRecordingList, NativeRecordingRow } from "./nativeRecordingsApi";
import "./nativeRecordings.css";

export function NativeRecordings() {
  const [page, setPage] = useState<NativeRecordingList | null>(null);
  const [cursor, setCursor] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setPage(null);
    setError(null);
    getNativeRecordings(cursor, controller.signal).then((value) => {
      if (active) setPage(value);
    }).catch((reason: Error) => {
      if (active && reason.name !== "AbortError") setError(reason.message);
    });
    return () => { active = false; controller.abort(); };
  }, [cursor, refresh]);
  return <main className="workspace native-workspace">
    <aside className="browser-pane" aria-label="Native recording browser">
      <h2>Native refinement</h2>
      <p>60 MS/s · full 300-symbol pilot</p>
      <button type="button" onClick={() => setRefresh((value) => value + 1)}>Refresh recordings</button>
      {error && <p role="alert">{error}</p>}
      {!page && !error && <p role="status">Loading native recordings…</p>}
      {page && <>
        <p>{page.total} registered episodes</p>
        {page.total === 0 && <p>No native recordings have been registered.</p>}
        <ul className="native-recording-list">
          {page.items.map((entry) => <li key={entry.bundle_id}>
            {entry.summary ? <button type="button" aria-pressed={selected === entry.bundle_id}
              onClick={() => setSelected(entry.bundle_id)}>
              <strong>Visit {entry.summary.visit} · episode {entry.summary.episode_index + 1}</strong>
              <span>{entry.summary.serial}</span>
              <span>{entry.summary.supported_count} / {entry.summary.head_count} supported</span>
              <span>Run: {entry.summary.owner_status.replaceAll("_", " ")}</span>
            </button> : <p role="status">Recording {entry.bundle_id.slice(0, 12)}: integrity unavailable</p>}
          </li>)}
        </ul>
        <nav aria-label="Native recording pages">
          <button type="button" disabled={cursor === 0} onClick={() => setCursor(Math.max(0, cursor - 20))}>Previous recordings</button>
          <button type="button" disabled={page.next_cursor === null} onClick={() => setCursor(page.next_cursor!)}>Next recordings</button>
        </nav>
      </>}
    </aside>
    <section className="detail-pane native-detail" aria-label="Native recording detail">
      {selected ? <Episode key={`${selected}-${refresh}`} id={selected} /> : <p>Select a native recording to review its measurements.</p>}
    </section>
  </main>;
}

function Episode({ id }: { id: string }) {
  const [cursor, setCursor] = useState(0);
  const [detail, setDetail] = useState<NativeRecordingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setDetail(null);
    setError(null);
    getNativeRecording(id, cursor, controller.signal).then((value) => {
      if (active) setDetail(value);
    }).catch((reason: Error) => {
      if (active && reason.name !== "AbortError") setError(reason.message);
    });
    return () => { active = false; controller.abort(); };
  }, [id, cursor]);
  if (error) return <p role="alert">{error}</p>;
  if (!detail || detail.cursor !== cursor) return <p role="status">Verifying native recording…</p>;
  const summary = detail.summary;
  return <>
    <h2>Visit {summary.visit} · episode {summary.episode_index + 1}</h2>
    <p><strong>Run outcome: {summary.owner_status.replaceAll("_", " ")}</strong> · controller result {summary.runtime_result}</p>
    <p>{summary.supported_count} supported · {summary.rejected_count} rejected · {summary.observed_start_span_s?.toFixed(3) ?? "—"} s between first and last measurement</p>
    <p className="native-evidence-note">CFO is relative to the receiver. These retained results have not qualified physical precision, acquisition, or original native-IQ verification.</p>
    <details><summary>Source identity</summary>
      <dl><dt>Radio</dt><dd>{summary.serial}</dd><dt>Boot</dt><dd>{summary.boot_id}</dd>
        <dt>Epoch</dt><dd>{summary.epoch}</dd><dt>Firmware digest</dt><dd>{summary.fit_sha256}</dd>
        <dt>Recording digest</dt><dd>{summary.bundle_id}</dd></dl>
    </details>
    <CfoPlot rows={detail.rows} />
    <p>Timing correction is relative to the scheduled pilot start. Rejected fits remain in the table and are excluded from the plot.</p>
    <div className="native-table-scroll"><table aria-label="Native measurements">
      <thead><tr><th>Frame</th><th>Coarse recording time (s)</th><th>Timing correction (ns)</th><th>CFO (Hz)</th><th>Coherence</th><th>Fit</th><th>Native sample</th></tr></thead>
      <tbody>{detail.rows.map(({ measurement: row, coarse_relative_scheduled_start_s: time }) => <tr key={row.sequence}>
        <td>{row.frame}</td><td>{time.toFixed(6)}</td><td>{(row.delay_s * 1e9).toFixed(2)}</td>
        <td>{row.cfo_hz.toFixed(2)}</td><td>{row.coherence.toFixed(4)}</td>
        <td>{row.supported ? "Supported" : `Rejected (mask ${row.rejection}, fault ${row.hardware_fault})`}</td>
        <td>{row.native_start_sample}</td>
      </tr>)}</tbody>
    </table></div>
    <nav aria-label="Native measurement pages">
      <button type="button" disabled={cursor === 0} onClick={() => setCursor(Math.max(0, cursor - 200))}>Previous measurements</button>
      <span>{detail.rows.length ? cursor + 1 : 0}–{cursor + detail.rows.length} of {summary.head_count}</span>
      <button type="button" disabled={detail.next_cursor === null} onClick={() => setCursor(detail.next_cursor!)}>Next measurements</button>
    </nav>
  </>;
}

function CfoPlot({ rows }: { rows: NativeRecordingRow[] }) {
  const supported = rows.filter((row) => row.measurement.supported);
  if (!supported.length) return <p>No supported CFO measurements on this page.</p>;
  const times = rows.map((row) => row.coarse_relative_scheduled_start_s);
  const values = supported.map((row) => row.measurement.cfo_hz);
  const start = Math.min(...times), end = Math.max(...times);
  const low = Math.min(...values), high = Math.max(...values);
  return <figure className="native-cfo-plot">
    <figcaption>Supported CFO on this page · {low.toFixed(2)} to {high.toFixed(2)} Hz</figcaption>
    <svg viewBox="0 0 720 210" role="img" aria-label="Supported CFO versus time in the coarse recording">
      <path d="M60 15V175H700" fill="none" stroke="currentColor" />
      <text x="5" y="25">{high.toFixed(1)}</text><text x="5" y="170">{low.toFixed(1)}</text>
      <text x="60" y="200">{start.toFixed(4)} s</text><text x="700" y="200" textAnchor="end">{end.toFixed(4)} s</text>
      {supported.map((row) => <circle key={row.measurement.sequence} r="2.5"
        cx={60 + (end === start ? 0.5 : (row.coarse_relative_scheduled_start_s - start) / (end - start)) * 640}
        cy={175 - (high === low ? 0.5 : (row.measurement.cfo_hz - low) / (high - low)) * 150}>
        <title>Frame {row.measurement.frame}: {row.measurement.cfo_hz.toFixed(2)} Hz</title>
      </circle>)}
    </svg>
  </figure>;
}
