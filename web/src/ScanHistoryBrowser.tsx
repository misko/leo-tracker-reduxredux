import { useEffect, useState } from "react";
import "./shared-scans.css";

type Adaptive = { session_id: string; captured_at: string | null; recorded_at: string;
  mode: string; selected_edge?: string; sample_rate_hz: number; retained_visits: number;
  started_visits: number; terminal_state: string };
type Page = { items: Adaptive[]; total: number; next_cursor: number | null; limit?: number };
type Fast = { recording_id: string; state: string; edge?: string; captured_windows?: number;
  updated_utc_ns: number; started_utc_ns?: number; failure?: string };
export type ScanSelection = { id: string; mode: "adaptive" | "fast" };
type Row = ScanSelection & { time: number; timeLabel: string; description: string; state: string };

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`Scan history request failed (${response.status})`);
  return response.json() as Promise<T>;
}

/** Presentation-only merge: each capture retains its original public contract. */
const loadCurrentAdaptive = (cursor: number, signal: AbortSignal) =>
  get<Page>(`/api/v3/scanner/adaptive-sessions?cursor=${cursor}&limit=20`, signal);

export function ScanHistoryBrowser({ selectedId, onSelect, loadAdaptive = loadCurrentAdaptive }: {
  selectedId: string | null; onSelect: (selection: ScanSelection) => void;
  loadAdaptive?: (cursor: number, signal: AbortSignal) => Promise<Page | null>;
}) {
  const [cursor, setCursor] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [fast, setFast] = useState<Fast[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); let busy = false;
    setPage(null); setLoaded(false);
    async function refresh() {
      if (busy) return;
      busy = true;
      const results = await Promise.allSettled([
        loadAdaptive(cursor, controller.signal),
        get<{ items: Fast[] }>("/api/v1/fast-scans/automatic", controller.signal),
      ]);
      if (!controller.signal.aborted) {
        if (results[0].status === "fulfilled") setPage(results[0].value as Page | null);
        if (results[1].status === "fulfilled") setFast((results[1].value as { items: Fast[] }).items);
        setErrors(results.flatMap(result => result.status === "rejected" ? [String(result.reason)] : []));
        setLoaded(true);
      }
      busy = false;
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [cursor, loadAdaptive]);
  const rows: Row[] = [
    ...(filter === "fast" ? [] : (page?.items ?? []).map(c => ({
      id: c.session_id, mode: "adaptive" as const,
      time: Date.parse(c.captured_at ?? c.recorded_at),
      timeLabel: c.captured_at ? "Capture" : "Recording created",
      description: `${c.mode} · ${c.selected_edge ? `${c.selected_edge} edge · ` : ""}${c.sample_rate_hz / 1e6} MS/s · ${c.retained_visits.toLocaleString()} visits`,
      state: c.terminal_state === "completed" ? "capture complete" : c.terminal_state,
    }))),
    ...(filter === "adaptive" || (cursor !== 0 && filter !== "fast") ? [] : fast.map(c => ({
      id: c.recording_id, mode: "fast" as const,
      time: (c.started_utc_ns ?? c.updated_utc_ns) / 1e6,
      timeLabel: c.started_utc_ns ? "Capture requested" : "Analysis updated",
      description: `fast · ${c.edge ?? "unknown"} edge · CH1–8 · 2.5 MS/s · ${(c.captured_windows ?? 0).toLocaleString()} paired RX visits`,
      state: c.failure ? `${c.state}: ${c.failure}` : c.state === "complete" ? "analysis complete" : c.state,
    }))),
  ].sort((a, b) => b.time - a.time || a.id.localeCompare(b.id));
  useEffect(() => {
    if (selectedId === null && loaded && rows[0]) onSelect(rows[0]);
  }, [selectedId, loaded, rows, onSelect]);
  return <section className="persistent-hop-history adaptive-history" aria-label="Adaptive and fast scan history">
    <header><div><span>AUTOMATIC SCANS</span><h3>Adaptive and fast captures</h3></div></header>
    <label>Scan mode <select value={filter} onChange={e => { setFilter(e.target.value); setCursor(0); }}>
      <option value="all">All modes</option><option value="adaptive">Adaptive</option><option value="fast">Fast</option>
    </select></label>
    <p>Shared radio schedule · 5-minute captures · 10-minute gap. Stop drains the current capture and pauses both modes.</p>
    {errors.map((error, index) => <p role="alert" key={index}>{error}</p>)}
    {!loaded && !errors.length && <p>Loading scan history…</p>}
    {loaded && !page && !errors.length && <p>Adaptive history is unavailable; showing fast captures.</p>}
    <div className="persistent-hop-scroll adaptive-history-scroll"><table className="scanner-history-table" aria-label="Unified scan history">
      <thead><tr><th>Capture</th><th>Status</th></tr></thead>
      <tbody>{rows.map(row => <tr key={`${row.mode}:${row.id}`} className={selectedId === row.id ? "selected" : undefined}>
        <td><button type="button" className="scanner-row-button persistent-hop-row" onClick={() => onSelect(row)}>
          <time>{row.timeLabel}: {new Date(row.time).toLocaleString()}</time><code>{row.id}</code><small>{row.description}</small>
        </button></td><td>{row.state}</td>
      </tr>)}</tbody>
    </table></div>
    {filter !== "fast" && page && <div className="candidate-pagination scanner-pagination">
      <span>{page.total.toLocaleString()} adaptive captures · {fast.length} recent fast captures</span>
      <button disabled={cursor === 0} onClick={() => setCursor(Math.max(0, cursor - (page.limit ?? 20)))}>Newer adaptive captures</button>
      <button disabled={page.next_cursor === null} onClick={() => setCursor(page.next_cursor!)}>Older adaptive captures</button>
    </div>}
  </section>;
}
