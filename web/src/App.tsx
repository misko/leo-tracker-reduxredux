import { useEffect, useMemo, useState, Suspense, lazy } from "react";
import {
  getActiveQueue,
  getAcquisitionQueue,
  getCaptureControl,
  getControlStatus,
  getScannerAnalyses,
  getProductContent,
  getRecording,
  getRecordingRadioSetup,
  getStatus,
  reprocessRecording,
  runResearchAnalysis,
  searchRecordings,
  scannerAnalysisPngUrl,
  startCapture,
  stopCapture,
} from "./api";
import type { CaptureControlStateV1, ScannerAnalysisHistoryPageV2 } from "./api";
import "./sky.css";

// three.js is only needed to draw the globe, so the sky view is split out and
// fetched on demand: the recordings UI does not carry a renderer it never uses.
const SkyInterface = lazy(() =>
  import("./SkyView").then((module) => ({ default: module.SkyInterface })),
);
import { StandardAnalysis } from "./StandardAnalysis";
import type {
  AnalysisState,
  ActiveQueueV1,
  AcquisitionQueueV1,
  ProductContentV1,
  RecordingDetailV1,
  RecordingRadioSetupV2,
  RecordingSummaryV1,
  SeriesV1,
  SystemStatusV1,
} from "./contracts.generated";

const analysisStates: Array<[string, string]> = [
  ["", "All analysis states"],
  ["complete", "Complete"],
  ["partial", "Partial"],
  ["running", "Running"],
  ["queued", "Queued"],
  ["failed", "Failed"],
  ["no_result", "No result"],
];

type PrimaryView = "recordings" | "queue" | "scanner" | "sky";

export default function App() {
  const [view, setView] = useState<PrimaryView>("recordings");
  const [status, setStatus] = useState<SystemStatusV1 | null>(null);
  const [reprocessEnabled, setReprocessEnabled] = useState(false);
  const [researchEnabled, setResearchEnabled] = useState(false);
  const [recordings, setRecordings] = useState<RecordingSummaryV1[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecordingDetailV1 | null>(null);
  const [query, setQuery] = useState("");
  const [includeTest, setIncludeTest] = useState(true);
  const [analysisState, setAnalysisState] = useState("");
  const [lastRecordingAt, setLastRecordingAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [captureControl, setCaptureControl] = useState<CaptureControlStateV1 | null>(null);
  const [captureControlError, setCaptureControlError] = useState<string | null>(null);
  const [captureControlPending, setCaptureControlPending] = useState<"start" | "stop" | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getStatus(controller.signal).then(setStatus).catch((reason: Error) => setError(reason.message));
    getControlStatus(controller.signal).then((value) => {
      setReprocessEnabled(value.standard_reprocess_enabled);
      setResearchEnabled(value.research_reprocess_enabled);
    }).catch(() => {
      setReprocessEnabled(false);
      setResearchEnabled(false);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    let controller = new AbortController();
    const refresh = () => {
      controller.abort();
      controller = new AbortController();
      getCaptureControl(controller.signal).then((state) => {
        setCaptureControl((current) => current && current.generation > state.generation
          ? current
          : state);
        setCaptureControlError(null);
      }).catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setCaptureControl(null);
          setCaptureControlError(reason.message);
        }
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 2_000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);

  const updateCapture = async (action: "start" | "stop") => {
    if (captureControl === null || captureControlPending) return;
    setCaptureControlPending(action);
    setCaptureControlError(null);
    try {
      const state = action === "start" ? await startCapture() : await stopCapture();
      setCaptureControl((current) => current && current.generation > state.generation
        ? current
        : state);
    } catch (reason) {
      setCaptureControlError(reason instanceof Error ? reason.message : "Capture control failed");
    } finally {
      setCaptureControlPending(null);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => searchRecordings("", false, "", controller.signal)
      .then((response) => setLastRecordingAt(response.items[0]?.started_at ?? null))
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    void refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      searchRecordings(query, includeTest, analysisState, controller.signal)
        .then((response) => {
          setRecordings(response.items);
          setSelectedId((current) => {
            if (current && response.items.some((item) => item.session_id === current)) return current;
            return response.items[0]?.session_id ?? null;
          });
          setError(null);
        })
        .catch((reason: Error) => {
          if (reason.name !== "AbortError") setError(reason.message);
        })
        .finally(() => setLoading(false));
    }, 120);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, includeTest, analysisState]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    getRecording(selectedId, controller.signal)
      .then(setDetail)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [selectedId]);

  return (
    <div className="app-shell">
      <Header
        status={status}
        view={view}
        onView={setView}
        lastRecordingAt={lastRecordingAt}
        reprocessEnabled={reprocessEnabled}
        captureControl={captureControl}
        captureControlError={captureControlError}
        captureControlPending={captureControlPending}
        onStartCapture={() => void updateCapture("start")}
        onStopCapture={() => void updateCapture("stop")}
      />
      {view === "recordings" ? <main className="workspace">
        <RecordingBrowser
          recordings={recordings}
          selectedId={selectedId}
          query={query}
          includeTest={includeTest}
          analysisState={analysisState}
          loading={loading}
          onQuery={setQuery}
          onIncludeTest={setIncludeTest}
          onAnalysisState={setAnalysisState}
          onSelect={setSelectedId}
        />
        <section className="detail-pane" aria-label="Recording detail">
          {error ? <ErrorBanner message={error} /> : null}
          {detail ? <RecordingDetail detail={detail} reprocessEnabled={reprocessEnabled} researchEnabled={researchEnabled} /> : <EmptyDetail loading={loading} />}
        </section>
      </main> : view === "queue" ? <QueueView /> : view === "scanner" ? <ScannerView /> : <Suspense fallback={<main className="workspace"><p>Loading the sky view…</p></main>}><SkyInterface /></Suspense>}
    </div>
  );
}

function Header({
  status,
  view,
  onView,
  lastRecordingAt,
  reprocessEnabled,
  captureControl,
  captureControlError,
  captureControlPending,
  onStartCapture,
  onStopCapture,
}: {
  status: SystemStatusV1 | null;
  view: PrimaryView;
  onView: (view: PrimaryView) => void;
  lastRecordingAt: string | null;
  reprocessEnabled: boolean;
  captureControl: CaptureControlStateV1 | null;
  captureControlError: string | null;
  captureControlPending: "start" | "stop" | null;
  onStartCapture: () => void;
  onStopCapture: () => void;
}) {
  const used = status ? Math.round(status.storage.used_fraction * 100) : null;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          LT
        </div>
        <div>
          <p className="eyebrow">LEO TRACKER</p>
          <h1>Observation Console</h1>
        </div>
      </div>
      <nav className="primary-nav" aria-label="Primary views">
        <button
          type="button"
          aria-current={view === "recordings" ? "page" : undefined}
          onClick={() => onView("recordings")}
        >
          Recordings
        </button>
        <button
          type="button"
          aria-current={view === "queue" ? "page" : undefined}
          onClick={() => onView("queue")}
        >
          Queue
        </button>
        <button
          type="button"
          aria-current={view === "scanner" ? "page" : undefined}
          onClick={() => onView("scanner")}
        >
          Scanner
        </button>
        <button
          type="button"
          aria-current={view === "sky" ? "page" : undefined}
          onClick={() => onView("sky")}
        >
          Sky
        </button>
      </nav>
      <div className="system-strip" aria-label="System status">
        <div className="system-stat clock-stat">
          <span>Current time</span>
          <strong>{formatUtcClock(now)}</strong>
          <small>{lastRecordingAt === null ? "Last recording unavailable" : `${formatElapsed(now - Date.parse(lastRecordingAt))} since last recording`}</small>
        </div>
        <div className="system-stat">
          <span>Storage</span>
          <strong>{used === null ? "—" : `${used}% used`}</strong>
          <div className="meter" aria-label={used === null ? "Storage unavailable" : `${used}% used`}>
            <i style={{ width: `${used ?? 0}%` }} />
          </div>
        </div>
        <div className="system-stat">
          <span>Processing</span>
          <strong>{status ? `${status.backlog.queued} queued · ${status.backlog.running} active` : "—"}</strong>
          <small>{status?.backlog.failed ?? 0} failed</small>
        </div>
        <div className="operator-pill">
          <span className="status-dot" />
          {reprocessEnabled || captureControl !== null ? "Operator controls" : "Presentation only"}
        </div>
        <div className="capture-control" role="group" aria-label="Capture control">
          <span aria-live="polite">
            {captureControl === null
              ? "Capture state unavailable"
              : captureControl.observed_state === "running"
                ? "Capture running"
                : captureControl.observed_state === "pausing"
                  ? "Capture stopping"
                  : "Capture stopped"}
          </span>
          <button
            type="button"
            className="capture-control-button start"
            aria-label="Start capture"
            disabled={captureControl === null || captureControlPending !== null || captureControl.desired_state === "running"}
            onClick={onStartCapture}
          >
            {captureControlPending === "start" ? "Starting…" : "Start"}
          </button>
          <button
            type="button"
            className="capture-control-button stop"
            aria-label="Stop capture"
            title="Stop new capture admission; an active capture finishes safely"
            disabled={captureControl === null || captureControlPending !== null || captureControl.desired_state === "paused"}
            onClick={onStopCapture}
          >
            {captureControlPending === "stop" ? "Stopping…" : "Stop"}
          </button>
          {captureControlError ? <small role="alert">{captureControlError}</small> : null}
        </div>
      </div>
    </header>
  );
}

function ScannerView() {
  const [page, setPage] = useState<ScannerAnalysisHistoryPageV2 | null>(null);
  const [cursor, setCursor] = useState(0);
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => getScannerAnalyses(cursor, 20, controller.signal).then((result) => {
      setPage(result);
      setSelectedScanId((current) => current && result.items.some((item) => item.scan_id === current)
        ? current
        : result.items[0]?.scan_id ?? null);
      setError(null);
    }).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    void refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [cursor]);
  const selected = page?.items.find((item) => item.scan_id === selectedScanId) ?? null;
  const report = selected?.report ?? null;
  return <main className="workspace scanner-workspace">
    <aside className="browser-pane scanner-browser" aria-label="Scanner browser">
      <div className="browser-header">
        <div><p className="section-label">INTER-DWELL SCANNER</p><strong>{page === null ? "Loading…" : `${page.total} scans`}</strong></div>
      </div>
      {error ? <ErrorBanner message={error} /> : null}
      {page && page.items.length === 0 ? <p className="empty-list">No Standard scanner analysis has been published yet.</p> : null}
      {page && page.items.length > 0 ? <>
        <div className="scanner-history-scroll"><table className="scanner-history-table" aria-label="Scanner history">
          <thead><tr><th>Scan</th><th>Active</th></tr></thead>
          <tbody>{page.items.map((item) => {
            const activeResults = item.report.results.filter((result) => result.decision === "active");
            const inconclusive = item.report.results.some((result) => result.decision === "inconclusive");
            return <tr key={item.scan_id} className={selectedScanId === item.scan_id ? "selected" : undefined}>
              <td><button className="scanner-row-button" type="button" onClick={() => setSelectedScanId(item.scan_id)}>
                <time title="RF capture start">{new Date(item.captured_at).toLocaleString()}</time>
                <code>{item.scan_id}</code>
                <small>{item.report.radio_id} · {item.analysis_id}</small>
              </button></td>
              <td><strong>{activeResults.length}/{item.report.results.length}</strong><StatusBadge value={inconclusive ? "partial" : "complete"} /></td>
            </tr>;
          })}</tbody>
        </table></div>
        <div className="candidate-pagination scanner-pagination" aria-label="Scanner history pagination">
          <span>Showing {page.cursor + 1}–{page.cursor + page.items.length} of {page.total}</span>
          <div>
            <button type="button" disabled={page.cursor === 0} onClick={() => setCursor(Math.max(0, page.cursor - page.limit))}>Previous</button>
            <button type="button" disabled={page.next_cursor === null} onClick={() => page.next_cursor !== null && setCursor(page.next_cursor)}>Next</button>
          </div>
        </div>
      </> : null}
    </aside>
    <section className="detail-pane scanner-analysis-detail" aria-label="Scanner analysis detail">
      {report && selected ? <>
        <header className="recording-heading scanner-heading">
          <div><p className="section-label">STANDARD SCAN ANALYSIS</p><h2>Starlink channel scans</h2><p className="recording-subtitle">{report.scan_id}</p></div>
          <div className="run-card"><span>CAPTURED AT</span><strong>{new Date(selected.captured_at).toLocaleString()}</strong><small>{selected.analysis_id}</small></div>
        </header>
        <section className="scanner-summary" aria-label="Scanner summary">
          <DataPair label="Scan" value={report.scan_id} />
          <DataPair label="Radio" value={report.radio_id} />
          <DataPair label="Capture" value={`${formatNumber(report.capture_elapsed_ms)} ms`} />
          <DataPair label="Analysis" value={`${formatNumber(report.analysis_elapsed_ms)} ms`} />
          <DataPair label="Geometry" value={`${report.configuration.dwell_ms} ms per target`} />
          <DataPair label="Evidence" value="Candidate-only GLRT64; no payload decoded" />
        </section>
        <section className="scanner-artifact-panel" aria-label="Scanner waterfall artifact">
          <header><div><span>STANDARD PNG</span><h3>Stitched waterfall</h3></div><small>Time increases downward · red lines mark retunes</small></header>
          <img src={scannerAnalysisPngUrl(selected.scan_id, selected.analysis_id, "waterfall")} alt={`Stitched waterfall for ${selected.scan_id}`} />
        </section>
        <section className="scanner-artifact-panel" aria-label="Scanner GLRT64 artifact">
          <header><div><span>STANDARD PNG</span><h3>Full-scan GLRT64 response</h3></div><small>Red lines mark retune boundaries</small></header>
          <img src={scannerAnalysisPngUrl(selected.scan_id, selected.analysis_id, "glrt64")} alt={`GLRT64 response for ${selected.scan_id}`} />
        </section>
        <div className="queue-table-scroll scanner-results-scroll"><table className="queue-table scanner-table" aria-label="Selected scanner results">
          <thead><tr><th>Channel</th><th>Edge</th><th>Decision</th><th>RF center</th><th>Applied IF</th><th>Best margin</th><th>Receiver</th><th>Tracking CFO</th><th>Reason</th></tr></thead>
          <tbody>{report.results.map((result) => <tr key={`${result.target.channel}-${result.target.edge}`}>
            <td>CH{result.target.channel}</td>
            <td>{result.target.edge}</td>
            <td><StatusBadge value={result.decision === "active" ? "complete" : result.decision === "inconclusive" ? "failed" : "no_result"} /></td>
            <td>{formatFrequency(result.target.rf_center_hz)}</td>
            <td>{result.actual_if_center_hz === null ? "—" : formatFrequency(result.actual_if_center_hz)}</td>
            <td>{result.best_margin === null ? "—" : result.best_margin.toFixed(4)}</td>
            <td>{result.first_detection === null ? "—" : `RX${result.first_detection.receiver_id}`}</td>
            <td>{result.first_detection === null ? "—" : `${formatNumber(result.first_detection.tracking_cfo_hz)} Hz`}</td>
            <td>{result.reason}</td>
          </tr>)}</tbody>
        </table></div>
      </> : <div className="empty-detail"><strong>{page === null ? "Loading scans…" : "Select a scan"}</strong><span>Standard waterfall and GLRT64 artifacts will appear here.</span></div>}
    </section>
  </main>;
}

function QueueView() {
  const [queue, setQueue] = useState<ActiveQueueV1 | null>(null);
  const [acquisitionQueue, setAcquisitionQueue] = useState<AcquisitionQueueV1 | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let controller = new AbortController();
    const refresh = () => {
      controller.abort();
      controller = new AbortController();
      Promise.all([
        getActiveQueue(controller.signal),
        getAcquisitionQueue(controller.signal),
      ]).then(([processing, acquisition]) => {
        setQueue(processing);
        setAcquisitionQueue(acquisition);
        setError(null);
      }).catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 2_000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);
  return (
    <main className="queue-page">
      <header className="queue-heading">
        <div><p className="section-label">PROCESSING</p><h2>Active and queued jobs</h2></div>
        <strong>{queue === null ? "Loading…" : `${queue.items.filter((job) => job.state === "leased").length} active · ${queue.items.filter((job) => job.state === "pending").length} queued`}</strong>
      </header>
      {error ? <ErrorBanner message={error} /> : null}
      <header className="queue-heading">
        <div><p className="section-label">RADIO OWNERSHIP</p><h2>Acquisition operations</h2></div>
        <strong>{acquisitionQueue === null ? "Loading…" : `${acquisitionQueue.items.filter((item) => item.state === "leased").length} active · ${acquisitionQueue.items.filter((item) => item.state === "pending").length} queued`}</strong>
      </header>
      {acquisitionQueue?.truncated ? <p className="queue-warning">Showing the first 200 acquisition operations.</p> : null}
      {acquisitionQueue && acquisitionQueue.items.length === 0 ? <p className="queue-empty">The acquisition queue is empty.</p> : null}
      {acquisitionQueue && acquisitionQueue.items.length > 0 ? <div className="queue-table-scroll"><table className="queue-table" aria-label="Acquisition operations">
        <thead><tr><th>State</th><th>Operation</th><th>Profile</th><th>Radios</th><th>Scheduled</th><th>Worker</th><th>Attempts</th></tr></thead>
        <tbody>{acquisitionQueue.items.map((operation) => <tr key={operation.operation_id}>
          <td><StatusBadge value={operation.state === "leased" ? "running" : "queued"} /></td>
          <td><strong>{operation.kind}</strong><small>{operation.operation_key}</small></td>
          <td>{operation.profile_name ?? "—"}</td>
          <td>{operation.radio_ids.length ? operation.radio_ids.join(" + ") : "Configured scanner radio"}</td>
          <td>{new Date(operation.scheduled_for).toLocaleString()}</td>
          <td>{operation.worker_id ?? "Waiting"}</td>
          <td>{operation.attempt_count}</td>
        </tr>)}</tbody>
      </table></div> : null}
      {queue?.truncated ? <p className="queue-warning">Showing the first 200 jobs.</p> : null}
      {queue && queue.items.length === 0 ? <p className="queue-empty">The processing queue is empty.</p> : null}
      {queue && queue.items.length > 0 ? <div className="queue-table-scroll"><table className="queue-table">
        <thead><tr><th>State</th><th>Work</th><th>Recording</th><th>Radio / receiver</th><th>Worker</th><th>Resource</th><th>Release</th></tr></thead>
        <tbody>{queue.items.map((job) => <tr key={job.job_id}>
          <td><StatusBadge value={job.state === "leased" ? "running" : "queued"} /></td>
          <td><strong>{job.stage_key}</strong><small>{job.description}</small></td>
          <td><code>{job.session_id}</code><small>{job.run_id}</small></td>
          <td>{job.radio_id ?? (job.scope_kind === "paired" ? "Both radios" : "—")}<small>{job.stream_id ?? ""}{job.receiver_id === null ? "" : ` · RX${job.receiver_id}`}</small></td>
          <td>{job.worker_id ?? "Waiting"}</td>
          <td>{job.resource_class}</td>
          <td><code>{job.pipeline_release_id.slice(0, 12)}…</code></td>
        </tr>)}</tbody>
      </table></div> : null}
    </main>
  );
}

interface BrowserProps {
  recordings: RecordingSummaryV1[];
  selectedId: string | null;
  query: string;
  includeTest: boolean;
  analysisState: string;
  loading: boolean;
  onQuery: (value: string) => void;
  onIncludeTest: (value: boolean) => void;
  onAnalysisState: (value: string) => void;
  onSelect: (value: string) => void;
}

function RecordingBrowser(props: BrowserProps) {
  return (
    <aside className="browser-pane" aria-label="Recording browser">
      <div className="browser-header">
        <div>
          <p className="section-label">RECORDINGS</p>
          <strong>{props.recordings.length} visible</strong>
        </div>
        {props.loading ? <span className="loading-pulse">Refreshing</span> : null}
      </div>
      <label className="search-field">
        <span>Search recordings</span>
        <input
          type="search"
          value={props.query}
          onChange={(event) => props.onQuery(event.target.value)}
          placeholder="Session, profile, tag…"
        />
      </label>
      <div className="filter-row">
        <label className="check-filter">
          <input
            type="checkbox"
            checked={props.includeTest}
            onChange={(event) => props.onIncludeTest(event.target.checked)}
          />
          Include TEST
        </label>
        <label className="select-filter">
          <span className="sr-only">Analysis state</span>
          <select
            value={props.analysisState}
            onChange={(event) => props.onAnalysisState(event.target.value)}
          >
            {analysisStates.map(([value, label]) => (
              <option value={value} key={value || "all"}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="recording-list">
        {props.recordings.map((recording) => (
          <button
            type="button"
            className={`recording-row ${recording.session_id === props.selectedId ? "selected" : ""}`}
            key={recording.session_id}
            onClick={() => props.onSelect(recording.session_id)}
          >
            <div className="row-topline">
              <span className={`source-badge source-${recording.source_type.toLowerCase()}`}>
                {recording.source_type}
              </span>
              <time title="RF capture start">Captured {formatDate(recording.started_at)}</time>
            </div>
            <strong>{recording.title}</strong>
            <span className="session-id">{recording.session_id}</span>
            <div className="row-footer">
              <StatusBadge value={recording.analysis.state} />
              <span>{recording.radio_count} radio{recording.radio_count === 1 ? "" : "s"}</span>
              <span>{formatDuration(recording.duration_seconds)}</span>
              {recording.hold.held ? <span className="held-mark">HELD</span> : null}
            </div>
          </button>
        ))}
        {!props.loading && props.recordings.length === 0 ? (
          <p className="empty-list">No recordings match these filters.</p>
        ) : null}
      </div>
    </aside>
  );
}

function RecordingDetail({ detail, reprocessEnabled, researchEnabled }: { detail: RecordingDetailV1; reprocessEnabled: boolean; researchEnabled: boolean }) {
  const current = detail.analysis.current_run;
  const [radioSetup, setRadioSetup] = useState<RecordingRadioSetupV2 | null>(null);
  const [radioSetupError, setRadioSetupError] = useState<string | null>(null);
  const [reprocessState, setReprocessState] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "queued"; runId: string; jobs: number }
    | { kind: "error"; message: string }
  >({ kind: "idle" });
  const [researchState, setResearchState] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "queued"; runId: string; jobs: number }
    | { kind: "error"; message: string }
  >({ kind: "idle" });
  const [analysisLane, setAnalysisLane] = useState<"standard" | "research">("standard");
  useEffect(() => {
    setReprocessState({ kind: "idle" });
    setResearchState({ kind: "idle" });
    setAnalysisLane("standard");
  }, [detail.session_id]);
  useEffect(() => {
    const controller = new AbortController();
    setRadioSetup(null);
    setRadioSetupError(null);
    getRecordingRadioSetup(detail.session_id, controller.signal).then(
      (result) => {
        setRadioSetup(result);
        setRadioSetupError(null);
      },
      (reason: Error) => {
        if (reason.name !== "AbortError") setRadioSetupError(reason.message);
      },
    );
    return () => controller.abort();
  }, [detail.session_id]);
  const submitReprocess = () => {
    setReprocessState({ kind: "submitting" });
    void reprocessRecording(detail.session_id).then(
      (result) => setReprocessState({
        kind: "queued",
        runId: result.run_id,
        jobs: result.queued_job_count,
      }),
      (reason: Error) => setReprocessState({ kind: "error", message: reason.message }),
    );
  };
  const submitResearch = () => {
    setResearchState({ kind: "submitting" });
    runResearchAnalysis(detail.session_id)
      .then((result) => setResearchState({
        kind: "queued",
        runId: result.run_id,
        jobs: result.queued_job_count,
      }))
      .catch((reason: Error) => setResearchState({ kind: "error", message: reason.message }));
  };
  const streamAnalyses = detail.stream_analyses?.length ? detail.stream_analyses : [{
    scope_key: "primary",
    radio_id: detail.radios[0]?.radio_id ?? "unknown-radio",
    receiver_labels: detail.radios[0]?.receiver_labels ?? [],
    is_primary: true,
    detection: detail.detection,
    whole_dwell: detail.whole_dwell,
    qam: detail.qam,
    doppler: detail.doppler,
  }];
  const primaryAnalysis = streamAnalyses.find((item) => item.is_primary) ?? streamAnalyses[0];
  return (
    <div className="detail-content">
      <header className="recording-heading">
        <div>
          <div className="heading-badges">
            <span className={`source-badge source-${detail.source_type.toLowerCase()}`}>
              {detail.source_type}
            </span>
            <StatusBadge value={detail.capture_health} />
            <StatusBadge value={detail.storage_state} />
            {detail.hold.held ? <span className="badge held">Held · {detail.hold.reason}</span> : null}
          </div>
          <h2>{detail.title}</h2>
          <p className="recording-subtitle">
            {detail.session_id} · {formatDateTime(detail.started_at)} · {formatDuration(detail.duration_seconds)}
          </p>
        </div>
        <div className="run-actions">
          <div className="run-card">
            <span>CURRENT ANALYSIS</span>
            <strong>{current?.pipeline_release ?? "No current run"}</strong>
            <small>{current?.run_id ?? detail.analysis.no_result_reason ?? detail.analysis.failure_reason}</small>
          </div>
          {reprocessEnabled ? (
            <button
              className="reprocess-button"
              type="button"
              disabled={reprocessState.kind === "submitting" || reprocessState.kind === "queued"}
              onClick={submitReprocess}
            >
              {reprocessState.kind === "submitting"
                ? "Queueing…"
                : reprocessState.kind === "queued"
                  ? "Analysis queued"
                  : "Re-run analysis"}
            </button>
          ) : null}
          {researchEnabled ? (
            <button
              className="reprocess-button research"
              type="button"
              disabled={researchState.kind === "submitting" || researchState.kind === "queued"}
              onClick={submitResearch}
            >
              {researchState.kind === "submitting"
                ? "Queueing Research…"
                : researchState.kind === "queued"
                  ? "Research queued"
                  : "Run Research analysis"}
            </button>
          ) : null}
          {reprocessState.kind === "queued" ? (
            <small className="reprocess-result" role="status">
              {reprocessState.jobs} jobs queued · {reprocessState.runId}. The current output remains visible until this run seals.
            </small>
          ) : null}
          {reprocessState.kind === "error" ? (
            <small className="reprocess-error" role="alert">{reprocessState.message}</small>
          ) : null}
          {researchState.kind === "queued" ? (
            <small className="reprocess-result" role="status">
              {researchState.jobs} Research jobs queued · {researchState.runId}. Standard remains independently current.
            </small>
          ) : null}
          {researchState.kind === "error" ? (
            <small className="reprocess-error" role="alert">{researchState.message}</small>
          ) : null}
        </div>
      </header>

      <RadioSetupTables setup={radioSetup} error={radioSetupError} />

      <AnalysisStateBanner detail={detail} />

      <nav className="analysis-lane-tabs" aria-label="Analysis pipeline lane">
        <button type="button" aria-current={analysisLane === "standard" ? "page" : undefined} onClick={() => setAnalysisLane("standard")}>Standard analysis<small>2×20 ms / 50 ms</small></button>
        <button type="button" aria-current={analysisLane === "research" ? "page" : undefined} onClick={() => setAnalysisLane("research")}>Research analysis<small>3×20 ms / 50 ms</small></button>
      </nav>
      <StandardAnalysis key={`${detail.session_id}:${analysisLane}`} sessionId={detail.session_id} includeTest={detail.source_type === "TEST"} lane={analysisLane} />

      <section className="metric-grid" aria-label="Key metrics">
        <Metric label="Radios" value={`${detail.radios.length}`} note={`${totalReceivers(detail)} receiver paths`} />
        <Metric
          label="Overlap"
          value={detail.synchronization.overlap_fraction === null ? "Single radio" : percent(detail.synchronization.overlap_fraction)}
          note={syncNote(detail)}
        />
        <Metric
          label="Primary QAM accuracy"
          value={primaryAnalysis.qam.combined_accuracy === null ? "No result" : percent(primaryAnalysis.qam.combined_accuracy)}
          note={`${primaryAnalysis.scope_key} · ${primaryAnalysis.qam.frame_count} known-pilot frames`}
          accent={primaryAnalysis.qam.combined_accuracy !== null}
        />
        <Metric
          label="Primary Doppler slope"
          value={primaryAnalysis.doppler.slope_hz_per_s === null ? "No result" : `${formatNumber(primaryAnalysis.doppler.slope_hz_per_s)} Hz/s`}
          note={`${primaryAnalysis.scope_key} · ${primaryAnalysis.doppler.association_status.replaceAll("_", " ")}`}
        />
      </section>

      <StageMatrix matrix={detail.stage_matrix ?? null} currentRunId={current?.run_id ?? null} tier={primaryAnalysis.whole_dwell.compute_tier} />

      <section className="panel acquisition-panel">
        <PanelHeading title="Acquisition geometry" eyebrow="PROFILE & RADIOS" aside={`profile r${detail.profile.revision}`} />
        <div className="profile-grid">
          <DataPair label="Profile" value={detail.profile.name} />
          <DataPair label="Sample rate" value={`${formatNumber(detail.profile.sample_rate_hz / 1e6)} MS/s`} />
          <DataPair label="RF bandwidth" value={`${formatNumber(detail.profile.bandwidth_hz / 1e6)} MHz`} />
        </div>
        <div className="radio-grid">
          {detail.radios.map((radio) => (
            <article className="radio-card" key={radio.radio_id}>
              <div>
                <span>{radio.radio_id}</span>
                <strong>{radio.receiver_labels.join(" · ")}</strong>
              </div>
              <StatusBadge value={radio.state} />
              <DataPair label="Serial" value={radio.serial} mono />
              <DataPair label="Gain" value={radio.gain_db.map((gain) => `${gain} dB`).join(" · ")} />
              <DataPair label="Samples" value={formatNumber(radio.captured_samples)} />
            </article>
          ))}
        </div>
        <div className="sync-strip">
          <div>
            <span>SYNCHRONIZATION</span>
            <strong>{detail.synchronization.mode.replaceAll("_", " ")} · {detail.synchronization.grade.replaceAll("_", " ")}</strong>
          </div>
          <DataPair label="Start skew" value={detail.synchronization.start_skew_ms === null ? "—" : `${detail.synchronization.start_skew_ms} ± ${detail.synchronization.skew_uncertainty_ms} ms`} />
          <DataPair label="Overlap" value={detail.synchronization.overlap_seconds === null ? "—" : `${detail.synchronization.overlap_seconds} s`} />
          <p>{detail.synchronization.timing_basis} · phase coherent: no</p>
        </div>
      </section>

      <section className="panel paths-panel">
        <PanelHeading title="Paths" eyebrow="LOCAL STORAGE" aside={detail.storage_state} />
        <PathRow label="Recording" value={detail.paths.recording_root} />
        <PathRow label="Manifest" value={detail.paths.manifest_path} />
        <PathRow label="Analysis" value={detail.paths.analysis_root ?? "No current analysis directory"} />
        {detail.radios.map((radio) => (
          <PathRow key={radio.radio_id} label={radio.radio_id} value={radio.raw_path ?? "Raw IQ purged"} />
        ))}
        {detail.products.map((product) => (
          <PathRow
            key={product.product_id}
            label={`${product.kind} · ${product.product_id}`}
            value={product.artifact_path}
          />
        ))}
      </section>

      <section className="panel provenance-panel">
        <PanelHeading title="Provenance" eyebrow="REPRODUCIBILITY" aside={`${detail.products.length} products`} />
        <div className="provenance-grid">
          <DataPair label="Recording digest" value={detail.provenance.recording_digest} mono />
          <DataPair label="Analysis run" value={detail.provenance.analysis_run_id ?? "Unavailable"} mono />
          <DataPair label="Configuration" value={detail.provenance.config_digest ?? "Unavailable"} mono />
          <DataPair label="Generated" value={detail.provenance.generated_at ? formatDateTime(detail.provenance.generated_at) : "Not complete"} />
        </div>
        <div className="tag-row">
          {detail.provenance.limitation_codes.map((code) => <span className="limitation" key={code}>{code}</span>)}
        </div>
      </section>
    </div>
  );
}

function RadioSetupTables({
  setup,
  error,
}: {
  setup: RecordingRadioSetupV2 | null;
  error: string | null;
}) {
  if (error) {
    return (
      <section className="radio-setup-state" role="alert">
        Radio setup unavailable · {error}
      </section>
    );
  }
  if (!setup) {
    return <section className="radio-setup-state" role="status">Loading captured radio setup…</section>;
  }
  return (
    <section className="radio-setup-section" aria-label="Captured radio setup">
      <div className="radio-setup-grid">
        {setup.radios.map((radio) => (
          <article className="radio-setup-card" key={radio.radio_id}>
            <header>
              <div><span>CAPTURED SETUP</span><h3>Radio {radio.radio_index}</h3></div>
              <code>{radio.radio_id}</code>
            </header>
            <table aria-label={`Radio ${radio.radio_index} captured setup`}>
              <tbody>
                <SetupRow label="Applied IF center" value={radio.applied_if_center_frequency_hz === null ? "Not applied" : formatFrequency(radio.applied_if_center_frequency_hz)} />
                <SetupRow label="Target RF center" value={radio.target_rf_center_frequency_hz === null ? "Not captured" : formatFrequency(radio.target_rf_center_frequency_hz)} />
                <SetupRow label="Applied RF bandwidth" value={radio.applied_bandwidth_hz === null ? "Not applied" : formatFrequency(radio.applied_bandwidth_hz)} />
                <SetupRow label="Applied sample rate" value={radio.applied_sample_rate_hz === null ? "Not applied" : `${formatNumber(radio.applied_sample_rate_hz / 1e6)} MS/s`} />
                <SetupRow label="Gain control" value={formatGainMode(radio.gain_mode)} />
                <SetupRow
                  label="Starlink target"
                  value={radio.starlink_channel === null || radio.starlink_edge === null
                    ? "Not captured"
                    : `Channel ${radio.starlink_channel.replace(/^ch/, "")} · ${radio.starlink_edge}`}
                />
                <SetupRow label="Firmware" value={radio.firmware_version ?? "Not reported"} mono />
              </tbody>
            </table>
          </article>
        ))}
      </div>
    </section>
  );
}

function SetupRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <tr><th scope="row">{label}</th><td className={mono ? "mono" : ""}>{value}</td></tr>;
}

type StreamAnalysis = RecordingDetailV1["stream_analyses"][number];

function StreamScientificEvidence({
  stream,
  products,
  currentRunId,
  dwellSeconds,
}: {
  stream: StreamAnalysis;
  products: RecordingDetailV1["products"];
  currentRunId: string | null;
  dwellSeconds: number;
}) {
  return (
    <section className="stream-analysis-group" aria-label={`Analysis ${stream.scope_key}`}>
      <header className="stream-analysis-heading">
        <div><span>RADIO / STREAM ANALYSIS</span><h3>{stream.radio_id}</h3></div>
        <strong>{stream.scope_key} · {stream.receiver_labels.join(" · ")}{stream.is_primary ? " · primary compatibility view" : ""}</strong>
      </header>
      <WholeDwellEvidence
        science={stream.whole_dwell}
        products={products}
        currentRunId={currentRunId}
        scopeKey={stream.scope_key}
        dwellSeconds={dwellSeconds}
      />
      <section className="evidence-grid">
        <article className="panel evidence-card">
          <PanelHeading title="Detection" eyebrow="STARLINK PILOT" aside={stream.detection.state} />
          <strong className="evidence-value">
            {stream.detection.known_pilot_candidate ? "Known pilot candidate" : "No candidate"}
          </strong>
          <DataPair label="Qin score" value={formatMaybe(stream.detection.qin_score, 4)} />
          <DataPair label="Control score" value={formatMaybe(stream.detection.control_score, 4)} />
          <p>{stream.detection.reason}</p>
          {!stream.detection.calibrated_detection ? <span className="limitation">Not a calibrated detection</span> : null}
        </article>
        <article className="panel evidence-card">
          <PanelHeading title="QAM" eyebrow="KNOWN SYMBOLS" aside={stream.qam.state} />
          <strong className="evidence-value">
            {stream.qam.combined_accuracy === null ? "No result" : percent(stream.qam.combined_accuracy)}
          </strong>
          <DataPair label="Receiver accuracy" value={stream.qam.receiver_accuracy.length ? stream.qam.receiver_accuracy.map(percent).join(" · ") : "—"} />
          <DataPair label="RMS EVM" value={formatMaybe(stream.qam.rms_evm, 3)} />
          {stream.qam.receiver_metrics.map((receiver) => (
            <div className="qam-receiver" key={receiver.receiver_key}>
              <DataPair
                label={`RX ${receiver.receiver_key}`}
                value={`${percent(receiver.accuracy)} · EVM ${receiver.rms_evm.toFixed(3)} · epoch ${receiver.candidate_epoch_sample}`}
              />
              <DataPair label="Baseband CFO offset" value={`${formatNumber(receiver.baseband_cfo_hz)} Hz`} />
              <DataPair label="Fine CFO refinement" value={`${formatNumber(receiver.residual_cfo_refinement_hz)} Hz`} />
              <DataPair label="Tuned-domain signal frequency" value={`${formatNumber(receiver.tuned_signal_frequency_hz)} Hz`} />
            </div>
          ))}
          <p>Predictable synchronization symbols only; user payload is not decoded.</p>
        </article>
        <article className="panel evidence-card">
          <PanelHeading title="Doppler" eyebrow="TRACK EVIDENCE" aside={stream.doppler.state} />
          <strong className="evidence-value">
            {stream.doppler.slope_hz_per_s === null ? "No track" : `${formatNumber(stream.doppler.slope_hz_per_s)} Hz/s`}
          </strong>
          <DataPair label="RX correlation" value={formatMaybe(stream.doppler.correlation, 4)} />
          <DataPair label="Baseband CFO at reference" value={stream.doppler.baseband_cfo_at_reference_hz === null ? "—" : `${formatNumber(stream.doppler.baseband_cfo_at_reference_hz)} Hz`} />
          <DataPair label="Tuned-domain frequency at reference" value={stream.doppler.tuned_signal_frequency_at_reference_hz === null ? "—" : `${formatNumber(stream.doppler.tuned_signal_frequency_at_reference_hz)} Hz`} />
          <DataPair label="Frequency span" value={stream.doppler.frequency_span_hz === null ? "—" : `${formatNumber(stream.doppler.frequency_span_hz)} Hz`} />
          <DataPair label="Residual RMS" value={stream.doppler.residual_rms_hz === null ? "—" : `${formatNumber(stream.doppler.residual_rms_hz)} Hz`} />
          <DataPair label="Track points" value={String(stream.doppler.point_count)} />
          <DataPair label="Motion / confidence" value={`${stream.doppler.motion_class ?? "indeterminate"} · ${stream.doppler.confidence}`} />
          <p>TLE: {stream.doppler.tle_candidate ?? stream.doppler.association_status.replaceAll("_", " ")}</p>
        </article>
      </section>
    </section>
  );
}

function WholeDwellEvidence({
  science,
  products,
  currentRunId,
  scopeKey,
  dwellSeconds,
}: {
  science: StreamAnalysis["whole_dwell"];
  products: RecordingDetailV1["products"];
  currentRunId: string | null;
  scopeKey: string;
  dwellSeconds: number;
}) {
  const coverage = science.candidate_coverage;
  const [sort, setSort] = useState<"margin" | "time" | "cfo">("margin");
  const [receiver, setReceiver] = useState("all");
  const [tracking, setTracking] = useState<"all" | "tracked" | "untracked">("all");
  const [minimumTime, setMinimumTime] = useState("");
  const [maximumTime, setMaximumTime] = useState("");
  const [minimumMargin, setMinimumMargin] = useState("");
  const [maximumRank, setMaximumRank] = useState("");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const receivers = useMemo(
    () => Array.from(new Set(science.candidates.map((candidate) => candidate.receiver_key))).sort(),
    [science.candidates],
  );
  const orderedCandidates = useMemo(() => {
    let candidates = receiver === "all"
      ? [...science.candidates]
      : science.candidates.filter((candidate) => candidate.receiver_key === receiver);
    if (tracking !== "all") candidates = candidates.filter((candidate) => (candidate.track_id !== null) === (tracking === "tracked"));
    const timeMin = Number.parseFloat(minimumTime);
    const timeMax = Number.parseFloat(maximumTime);
    const marginMin = Number.parseFloat(minimumMargin);
    const rankMax = Number.parseInt(maximumRank, 10);
    if (Number.isFinite(timeMin)) candidates = candidates.filter((candidate) => candidate.time_s >= timeMin);
    if (Number.isFinite(timeMax)) candidates = candidates.filter((candidate) => candidate.time_s <= timeMax);
    if (Number.isFinite(marginMin)) candidates = candidates.filter((candidate) => candidate.margin >= marginMin);
    if (Number.isFinite(rankMax)) candidates = candidates.filter((candidate) => candidate.rank_within_search <= rankMax);
    candidates.sort((left, right) => {
      if (sort === "time") return left.time_s - right.time_s;
      if (sort === "cfo") return left.baseband_cfo_hz - right.baseband_cfo_hz;
      return right.margin - left.margin;
    });
    return candidates;
  }, [maximumRank, maximumTime, minimumMargin, minimumTime, receiver, science.candidates, sort, tracking]);
  const pageCount = Math.max(1, Math.ceil(orderedCandidates.length / 20));
  const visibleCandidates = orderedCandidates.slice(page * 20, page * 20 + 20);
  const selected = orderedCandidates.find((candidate) => candidate.candidate_id === selectedId)
    ?? visibleCandidates[0]
    ?? null;

  useEffect(() => {
    setPage(0);
  }, [maximumRank, maximumTime, minimumMargin, minimumTime, receiver, sort, tracking]);
  const trackedCount = science.candidates.filter((candidate) => candidate.track_id !== null).length;
  return (
    <section className="panel science-panel" aria-label={`Whole-dwell candidate evidence ${scopeKey}`}>
      <PanelHeading
        title="Whole-dwell candidate evidence"
        eyebrow="BOUNDED SCIENTIFIC VIEW"
        aside={`${science.returned_candidate_count} / ${science.candidate_count} candidates`}
      />
      <div className="profile-grid science-summary">
        <DataPair label="Compute tier" value={science.compute_tier} />
        <DataPair label="Scientific confidence" value={science.confidence} />
        <DataPair label="Evidence run" value={science.analysis_run_id ?? "Not run"} mono />
        <DataPair
          label="Current-run match"
          value={science.analysis_run_id && science.analysis_run_id === currentRunId ? "verified" : "unavailable"}
        />
      </div>
      <p>{science.confidence_reason}</p>
      <AnalysisTierRail science={science} currentRunId={currentRunId} />
      {coverage ? (
        <div className="profile-grid candidate-coverage">
          <DataPair label="Survey windows" value={`${coverage.complete_windows} / ${coverage.scheduled_windows} complete`} />
          <DataPair label="Receiver windows" value={formatNumber(coverage.searched_receiver_windows)} />
          <DataPair label="Surveyed time" value={percent(coverage.searched_time_fraction)} />
          <DataPair label="Search residual CFO range" value={`${formatNumber(coverage.residual_cfo_min_hz)} to ${formatNumber(coverage.residual_cfo_max_hz)} Hz`} />
        </div>
      ) : <p className="plot-empty">Candidate coverage has not been published.</p>}
      <div className="candidate-explorer">
        <div className="candidate-toolbar">
          <strong>Candidate explorer</strong>
          <label>Receiver
            <select aria-label="Filter candidates by receiver" value={receiver} onChange={(event) => setReceiver(event.target.value)}>
              <option value="all">All receivers</option>
              {receivers.map((value) => <option value={value} key={value}>RX {value}</option>)}
            </select>
          </label>
          <label>Tracking
            <select aria-label="Filter candidates by tracking" value={tracking} onChange={(event) => setTracking(event.target.value as typeof tracking)}>
              <option value="all">Tracked and untracked</option>
              <option value="tracked">Tracked only</option>
              <option value="untracked">Untracked only</option>
            </select>
          </label>
          <label>Sort
            <select aria-label="Sort candidates" value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
              <option value="margin">Strongest margin</option>
              <option value="time">Time</option>
              <option value="cfo">Baseband CFO</option>
            </select>
          </label>
          <label>Time from (s)<input aria-label="Minimum candidate time" inputMode="decimal" value={minimumTime} onChange={(event) => setMinimumTime(event.target.value)} /></label>
          <label>Time to (s)<input aria-label="Maximum candidate time" inputMode="decimal" value={maximumTime} onChange={(event) => setMaximumTime(event.target.value)} /></label>
          <label>Margin at least<input aria-label="Minimum candidate margin" inputMode="decimal" value={minimumMargin} onChange={(event) => setMinimumMargin(event.target.value)} /></label>
          <label>Local rank at most<input aria-label="Maximum candidate rank" inputMode="numeric" value={maximumRank} onChange={(event) => setMaximumRank(event.target.value)} /></label>
        </div>
        <div className="candidate-accounting" aria-label="Candidate accounting">
          <span>{science.candidate_count} total</span><span>{science.returned_candidate_count} retained here</span>
          <span>{orderedCandidates.length} match filters</span><span>{trackedCount} tracked</span>
          <span>{science.returned_candidate_count - trackedCount} untracked</span>
          <span>{science.candidate_lineage_truncated ? `${science.candidate_count - science.returned_candidate_count} lineage rows truncated` : "lineage complete"}</span>
        </div>
        <div className="candidate-workspace">
          <div className="candidate-table-wrap">
            <table className="candidate-table" aria-label="Candidate lineage">
              <thead><tr><th>Time</th><th>RX</th><th>Baseband CFO</th><th>Margin</th><th>Track</th></tr></thead>
              <tbody>
                {visibleCandidates.map((candidate) => (
                  <tr key={candidate.candidate_id} className={candidate.candidate_id === selected?.candidate_id ? "selected" : ""}>
                    <td><button type="button" onClick={() => setSelectedId(candidate.candidate_id)} aria-label={`Inspect candidate ${candidate.candidate_id}`}>{candidate.time_s.toFixed(3)} s</button></td>
                    <td>RX {candidate.receiver_key}</td>
                    <td>{formatNumber(candidate.baseband_cfo_hz)} Hz</td>
                    <td>{candidate.margin.toFixed(4)}</td>
                    <td>{candidate.track_id ?? "untracked"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visibleCandidates.length ? <p className="candidate-empty">No candidates match this receiver.</p> : null}
            <div className="candidate-pagination">
              <span>{orderedCandidates.length ? `${page * 20 + 1}–${Math.min((page + 1) * 20, orderedCandidates.length)} of ${orderedCandidates.length}` : "0 candidates"}</span>
              <div><button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => value + 1)}>Next 20</button></div>
            </div>
          </div>
          <CandidateInspector candidate={selected} />
        </div>
      </div>
      <div className="control-strip">
        <DataPair label="Control state" value={science.controls.state} />
        <DataPair label="Passed research gate" value={String(science.controls.passed_candidate_count)} />
        <DataPair label="Thresholds calibrated" value={science.controls.thresholds_calibrated ? "yes" : "no"} />
        <DataPair label="Specificity claimed" value={science.controls.specificity_claimed ? "yes" : "no"} />
        <p>{science.controls.reason}</p>
        {science.controls.rejection_reasons.map((reason) => <span className="limitation" key={reason}>{reason}</span>)}
      </div>
      <OverlayPlot products={products} currentRunId={currentRunId} scopeKey={scopeKey} dwellSeconds={dwellSeconds} />
    </section>
  );
}

function AnalysisTierRail({ science, currentRunId }: { science: StreamAnalysis["whole_dwell"]; currentRunId: string | null }) {
  const tiers = ["quick", "standard", "research"] as const;
  return (
    <div className="tier-rail" aria-label="Analysis tier status">
      {tiers.map((tier) => {
        const published = science.compute_tier === tier && science.analysis_run_id === currentRunId;
        return <div key={tier}><span>{tier}</span><strong className={published ? "tier-published" : ""}>{published ? "Published for current run" : "Not run / no published result"}</strong></div>;
      })}
    </div>
  );
}

function StageMatrix({ matrix, currentRunId, tier }: { matrix: RecordingDetailV1["stage_matrix"]; currentRunId: string | null; tier: StreamAnalysis["whole_dwell"]["compute_tier"] }) {
  const verified = matrix && currentRunId && matrix.analysis_run_id === currentRunId ? matrix : null;
  const tierLabel = tier === "not_run" ? "Current-run" : `${tier[0].toUpperCase()}${tier.slice(1)}`;
  return (
    <details className="panel stage-matrix" aria-label={`${tierLabel} stage completion matrix`}>
      <summary><PanelHeading title={`${tierLabel} stage completion`} eyebrow="CATALOG JOB STATUS" aside={verified ? `${verified.returned_stage_count} / ${verified.source_stage_count} stages` : "unavailable"} /></summary>
      {!verified ? <p className="stage-unavailable">No verified current-run stage inventory is available. Product presence is not used as a substitute for execution status.</p> : (
        <>
          <p className="stage-caveat">Catalog-backed job outcomes for run <code>{verified.analysis_run_id}</code>. These rows do not claim signal-time coverage or per-stage runtime.</p>
          <div className="stage-table-wrap">
            <table className="stage-table">
              <thead><tr><th>Stage</th><th>Scope</th><th>Execution</th><th>Scientific outcome</th></tr></thead>
              <tbody>{verified.stages.map((stage) => (
                <tr key={`${stage.stage_key}-${stage.scope_key}`}>
                  <td>{stage.stage_key}</td><td>{stage.scope_key}</td><td><StatusBadge value={stage.state} /></td><td>{stage.outcome?.replaceAll("_", " ") ?? "not yet reported"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {verified.truncated ? <p className="limitation">Stage inventory is truncated; {verified.source_stage_count - verified.returned_stage_count} rows are not displayed.</p> : null}
        </>
      )}
    </details>
  );
}

function CandidateInspector({ candidate }: { candidate: StreamAnalysis["whole_dwell"]["candidates"][number] | null }) {
  if (!candidate) return <aside className="candidate-inspector"><strong>No candidate selected</strong></aside>;
  return (
    <aside className="candidate-inspector" aria-label="Selected candidate detail">
      <header><span>SELECTED CANDIDATE</span><strong title={candidate.candidate_id}>{candidate.candidate_id}</strong></header>
      <DataPair label="Track / RX" value={`${candidate.track_id ?? "untracked"} · RX ${candidate.receiver_key}`} />
      <DataPair label="Epoch" value={`${candidate.absolute_epoch_sample} · ${candidate.time_s.toFixed(6)} s`} />
      <DataPair label="Baseband CFO" value={`${formatNumber(candidate.baseband_cfo_hz)} Hz`} />
      <DataPair label="Search residual CFO" value={`${formatNumber(candidate.search_residual_cfo_hz)} Hz`} />
      <DataPair label="Receiver tuned center" value={`${formatNumber(candidate.receiver_tuned_center_hz)} Hz`} />
      <DataPair label="Tuned signal frequency" value={`${formatNumber(candidate.tuned_signal_frequency_hz)} Hz`} />
      <DataPair label="Verification / control" value={`${candidate.verify_score.toFixed(4)} / ${candidate.control_score.toFixed(4)}`} />
      <DataPair label="Margin / rank" value={`${candidate.margin.toFixed(4)} · ${candidate.rank_within_search}`} />
      <details><summary>Evidence lineage</summary><code>{candidate.calibration_digest}</code><code>{candidate.parent_survey_config_digest}</code></details>
    </aside>
  );
}

function AnalysisStateBanner({ detail }: { detail: RecordingDetailV1 }) {
  if (detail.analysis.state === "complete") return null;
  const message = detail.analysis.failure_reason ?? detail.analysis.no_result_reason ?? detail.analysis.coverage?.description ?? "Analysis is in progress";
  return (
    <div className={`state-banner state-${detail.analysis.state}`} role="status">
      <strong>{detail.analysis.state.replaceAll("_", " ")}</strong>
      <span>{message}</span>
    </div>
  );
}

function PowerPlot({ series, dwellSeconds }: { series: SeriesV1[]; dwellSeconds: number }) {
  const points = series[0]?.points ?? [];
  const bounds = useMemo(() => {
    const values = points.map((point) => point.value);
    return { min: Math.min(...values, 0), max: Math.max(...values, 1) };
  }, [points]);
  if (!points.length) return <div className="plot-empty">Power product unavailable</div>;
  return (
    <div className="power-plot" aria-label="Power timeline">
      <div className="plot-bars">
        {points.map((point) => {
          const height = 18 + ((point.value - bounds.min) / (bounds.max - bounds.min || 1)) * 72;
          return <i key={point.time_s} style={{ height: `${height}%`, left: `${Math.min(100, Math.max(0, point.time_s / Math.max(dwellSeconds, 0.001) * 100))}%` }} title={`${point.time_s}s · ${point.value.toFixed(2)}`} />;
        })}
      </div>
      <TimeAxis dwellSeconds={dwellSeconds} />
      <div className="plot-legend">{series.map((item) => <span key={item.series_id}>{item.label} · {item.unit}</span>)}</div>
    </div>
  );
}

function Waterfall({ products, currentRunId, scopeKey, dwellSeconds }: { products: RecordingDetailV1["products"]; currentRunId: string | null; scopeKey: string; dwellSeconds: number }) {
  const product = products.find((item) => item.kind === "waterfall" && (scopeKey === "primary" || item.summary.scope_key === scopeKey));
  const [content, setContent] = useState<ProductContentV1 | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!product) {
      setContent(null);
      return;
    }
    const controller = new AbortController();
    setContent(null);
    setFailed(false);
    getProductContent(product.product_id, controller.signal)
      .then((result) => {
        if (!currentRunId || result.analysis_run_id !== currentRunId || result.analysis_run_id !== product.analysis_run_id) {
          setFailed(true);
          setContent(null);
          return;
        }
        setContent(result);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [product, currentRunId, scopeKey]);
  if (!product) return <div className="waterfall-empty">No waterfall product for this run.</div>;
  if (failed) return <div className="waterfall-empty">Registered waterfall could not be verified.</div>;
  if (!content) return <div className="waterfall-empty">Loading bounded waterfall…</div>;
  const frequencies = content.points.map((point) => point.y).filter(Number.isFinite);
  const frequencyMin = frequencies.length ? Math.min(...frequencies) : 0;
  const frequencyMax = frequencies.length ? Math.max(...frequencies) : 0;
  const frequencyRange = frequencyMax - frequencyMin || 1;
  return (
    <div className="waterfall-block">
      <div className="waterfall-y-axis" aria-hidden="true"><span>{formatNumber(frequencyMax)} Hz</span><span>{formatNumber(frequencyMin)} Hz</span></div>
      <svg className="waterfall" aria-label="Waterfall plot" role="img" viewBox="0 0 1000 220" preserveAspectRatio="none">
        {content.points.map((point, index) => (
          <circle
            key={`${point.x}-${point.y}-${index}`}
            cx={Math.min(1000, Math.max(0, point.x / Math.max(dwellSeconds, 0.001) * 1000))}
            cy={220 - Math.min(220, Math.max(0, (point.y - frequencyMin) / frequencyRange * 220))}
            r="4"
            fill={heatColor(point.value)}
          ><title>{`${point.x}s · ${formatNumber(point.y)} Hz · normalized power ${point.value.toFixed(4)}`}</title></circle>
        ))}
      </svg>
      <TimeAxis dwellSeconds={dwellSeconds} />
      <div className="waterfall-footer">
        <span>{content.returned_point_count} / {content.source_point_count} display points</span>
        <span>x: {String(content.metadata.time_unit ?? "s")} · y: {String(content.metadata.frequency_unit ?? "Hz")} · color: {String(content.metadata.value_unit ?? "normalized power")}</span>
        <span>{content.truncated ? "deterministically decimated" : "all source points shown"}</span>
      </div>
    </div>
  );
}

function OverlayPlot({ products, currentRunId, scopeKey, dwellSeconds }: { products: RecordingDetailV1["products"]; currentRunId: string | null; scopeKey: string; dwellSeconds: number }) {
  const product = products.find((item) => item.kind === "overlays" && (scopeKey === "primary" || item.summary.scope_key === scopeKey));
  const [content, setContent] = useState<ProductContentV1 | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!product || !currentRunId) {
      setContent(null);
      return;
    }
    const controller = new AbortController();
    setContent(null);
    setFailed(false);
    getProductContent(product.product_id, controller.signal)
      .then((result) => {
        if (result.analysis_run_id === currentRunId && result.analysis_run_id === product.analysis_run_id) setContent(result);
        else setFailed(true);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [product, currentRunId, scopeKey]);
  if (!product) return <p className="plot-empty">Candidate overlays have not been published.</p>;
  if (failed) return <p className="plot-empty">Registered candidate overlays could not be verified.</p>;
  if (!content) return <p className="plot-empty">Loading verified candidate overlays…</p>;
  const yValues = content.points.map((point) => point.y).filter(Number.isFinite);
  const yMin = yValues.length ? Math.min(...yValues) : 0;
  const yMax = yValues.length ? Math.max(...yValues) : 0;
  const yRange = yMax - yMin || 1;
  return (
    <div className="overlay-block">
      <div className="overlay-y-axis"><span>{formatNumber(yMax)} Hz</span><span>{formatNumber(yMin)} Hz</span></div>
      <div className="overlay-plot" aria-label="Candidate overlay plot">
      {content.points.map((point, index) => (
        <i
          key={`${point.x}-${point.y}-${index}`}
          style={{ left: `${Math.min(100, Math.max(0, point.x / Math.max(dwellSeconds, 0.001) * 100))}%`, bottom: `${Math.min(100, Math.max(0, (point.y - yMin) / yRange * 100))}%` }}
          title={`${point.x}s · ${formatNumber(point.y)} Hz · margin ${point.value.toFixed(4)}`}
        />
      ))}
      <span>{content.returned_point_count} bounded candidate overlays · run {content.analysis_run_id}</span>
      </div>
      <TimeAxis dwellSeconds={dwellSeconds} />
    </div>
  );
}

function TimeAxis({ dwellSeconds }: { dwellSeconds: number }) {
  return <div className="plot-axis time-axis" aria-label={`Time axis 0 to ${dwellSeconds} seconds`}><span>0 s</span><span>{(dwellSeconds / 2).toFixed(dwellSeconds < 10 ? 1 : 0)} s</span><span>{dwellSeconds.toFixed(dwellSeconds < 10 ? 1 : 0)} s</span></div>;
}

function PanelHeading({ title, eyebrow, aside }: { title: string; eyebrow: string; aside: string }) {
  return <header className="panel-heading"><div><span>{eyebrow}</span><h3>{title}</h3></div><small>{aside.replaceAll("_", " ")}</small></header>;
}

function Metric({ label, value, note, accent = false }: { label: string; value: string; note: string; accent?: boolean }) {
  return <article className={`metric ${accent ? "accent" : ""}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function DataPair({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="data-pair"><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div>;
}

function PathRow({ label, value }: { label: string; value: string }) {
  return <div className="path-row"><span>{label}</span><code>{value}</code></div>;
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`badge status-${value}`}>{value.replaceAll("_", " ")}</span>;
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="error-banner" role="alert"><strong>Unable to load presentation data</strong><span>{message}</span></div>;
}

function EmptyDetail({ loading }: { loading: boolean }) {
  return <div className="empty-detail"><strong>{loading ? "Loading recordings…" : "Select a recording"}</strong><span>Analysis evidence and exact storage paths will appear here.</span></div>;
}

function totalReceivers(detail: RecordingDetailV1): number {
  return detail.radios.reduce((total, radio) => total + radio.receiver_labels.length, 0);
}

function syncNote(detail: RecordingDetailV1): string {
  if (detail.synchronization.mode === "none") return detail.synchronization.timing_basis;
  return `${detail.synchronization.overlap_seconds ?? 0} s overlap · ${detail.synchronization.grade}`;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(value < 0.01 ? 3 : 1)}%`;
}

function formatMaybe(value: number | null, digits: number): string {
  return value === null ? "—" : value.toFixed(digits);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatFrequency(valueHz: number): string {
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(valueHz / 1e6)} MHz`;
}

function formatGainMode(value: RecordingRadioSetupV2["radios"][number]["gain_mode"]): string {
  if (value === null) return "Not applied";
  if (value === "slow_attack") return "Slow-attack AGC";
  if (value === "fast_attack") return "Fast-attack AGC";
  if (value === "hybrid") return "Hybrid AGC";
  return "Manual";
}

function formatDuration(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(seconds % 1 ? 2 : 0)} s`;
}

function formatUtcClock(timestampMs: number): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(timestampMs) + " UTC";
}

function formatElapsed(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1_000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value)) + " UTC";
}

function heatColor(value: number): string {
  const bounded = Math.max(0, Math.min(1, value));
  return `hsl(${190 - bounded * 150} 72% ${12 + bounded * 54}%)`;
}

export type { AnalysisState };
