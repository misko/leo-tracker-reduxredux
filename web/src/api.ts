import type {
  ProductContentV1,
  ActiveQueueV1,
  AcquisitionQueueV1,
  RecordingDetailV1,
  RecordingRadioSetupV2,
  RecordingSearchResponseV1,
  SystemStatusV1,
} from "./contracts.generated";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "GET", signal });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export interface CaptureControlStateV1 {
  schema_version: 1;
  generation: number;
  desired_state: "running" | "paused";
  observed_state: "running" | "pausing" | "paused";
  changed_utc_ns: number;
  operator_id: string;
  reason: string;
}

export function getCaptureControl(signal?: AbortSignal): Promise<CaptureControlStateV1> {
  return getJson<CaptureControlStateV1>("/api/v1/capture-control", signal);
}

export function stopCapture(): Promise<CaptureControlStateV1> {
  return postJson<CaptureControlStateV1>("/api/v1/capture-control/stop");
}

export function startCapture(): Promise<CaptureControlStateV1> {
  return postJson<CaptureControlStateV1>("/api/v1/capture-control/start");
}

export interface StandardReprocessResultV1 {
  schema_version: 1;
  session_id: string;
  run_id: string;
  pipeline_release_id: string;
  previous_current_run_id: string | null;
  queued_job_count: number;
  state: "queued";
}

export interface AnalysisControlStatusV2 {
  schema_version: 2;
  standard_reprocess_enabled: boolean;
  research_reprocess_enabled: boolean;
}

export interface ResearchReprocessResultV1 {
  schema_version: 1;
  pipeline_lane: "research";
  session_id: string;
  run_id: string;
  pipeline_release_id: string;
  previous_research_run_id: string | null;
  queued_job_count: number;
  scheduling_priority: "lower_than_standard";
  state: "queued";
}

export interface ScannerReportV1 {
  schema_version: 1;
  kind: "starlink_scanner_report";
  scan_id: string;
  radio_id: string;
  radio_serial: string;
  capture_elapsed_ms: number;
  analysis_elapsed_ms: number;
  candidate_only: true;
  payload_decoded: false;
  configuration: {
    dwell_ms: number;
    gain_mode: string;
    gain_db: number;
    glrt64_margin_gate: number;
  };
  results: Array<{
    target: { channel: number; edge: "lower" | "upper"; rf_center_hz: number; if_center_hz: number };
    decision: "active" | "no_detection" | "inconclusive";
    requested_if_center_hz: number;
    actual_if_center_hz: number | null;
    best_margin: number | null;
    first_detection: null | {
      receiver_id: number;
      probe_start_ms: number;
      tracking_cfo_hz: number;
      margin: number;
    };
    reason: string;
  }>;
}

export interface ScannerHistoryPageV1 {
  schema_version: 1;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{ schema_version: 1; scanned_at: string; report: ScannerReportV1 }>;
}

export interface ScannerAnalysisHistoryPageV2 {
  schema_version: 2;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 2;
    captured_at: string;
    published_at: string;
    scan_id: string;
    analysis_id: string;
    report: ScannerReportV1;
  }>;
}

export function getScannerReports(
  cursor = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<ScannerHistoryPageV1> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<ScannerHistoryPageV1>(`/api/v1/scanner/reports?${params}`, signal);
}

export function getScannerAnalyses(
  cursor = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<ScannerAnalysisHistoryPageV2> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<ScannerAnalysisHistoryPageV2>(`/api/v2/scanner/analyses?${params}`, signal);
}

export function scannerAnalysisPngUrl(
  scanId: string,
  analysisId: string,
  artifact: "waterfall" | "glrt64",
): string {
  return `/api/v1/scanner/analyses/${encodeURIComponent(scanId)}/${encodeURIComponent(analysisId)}/${artifact}.png`;
}

export function getStatus(signal?: AbortSignal): Promise<SystemStatusV1> {
  return getJson<SystemStatusV1>("/api/v1/status", signal);
}

export function getControlStatus(signal?: AbortSignal): Promise<AnalysisControlStatusV2> {
  return getJson<AnalysisControlStatusV2>("/api/v2/control/status", signal);
}

export function getActiveQueue(signal?: AbortSignal): Promise<ActiveQueueV1> {
  return getJson<ActiveQueueV1>("/api/v1/queue?limit=200", signal);
}

export function getAcquisitionQueue(signal?: AbortSignal): Promise<AcquisitionQueueV1> {
  return getJson<AcquisitionQueueV1>("/api/v1/acquisition-queue?limit=200", signal);
}

export function searchRecordings(
  query: string,
  includeTest: boolean,
  analysisState: string,
  signal?: AbortSignal,
): Promise<RecordingSearchResponseV1> {
  const params = new URLSearchParams({
    include_test: String(includeTest),
    limit: "100",
  });
  if (query.trim()) params.set("query", query.trim());
  if (analysisState) params.set("analysis_state", analysisState);
  return getJson<RecordingSearchResponseV1>(`/api/v1/recordings?${params}`, signal);
}

export function getRecording(sessionId: string, signal?: AbortSignal): Promise<RecordingDetailV1> {
  return getJson<RecordingDetailV1>(`/api/v1/recordings/${encodeURIComponent(sessionId)}`, signal);
}

export function getRecordingRadioSetup(
  sessionId: string,
  signal?: AbortSignal,
): Promise<RecordingRadioSetupV2> {
  return getJson<RecordingRadioSetupV2>(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/radio-setup`,
    signal,
  );
}

export function reprocessRecording(sessionId: string): Promise<StandardReprocessResultV1> {
  return postJson<StandardReprocessResultV1>(
    `/api/v2/control/recordings/${encodeURIComponent(sessionId)}/reprocess`,
  );
}

export function runResearchAnalysis(sessionId: string): Promise<ResearchReprocessResultV1> {
  return postJson<ResearchReprocessResultV1>(
    `/api/v2/control/recordings/${encodeURIComponent(sessionId)}/research`,
  );
}

export function getProductContent(
  productId: string,
  signal?: AbortSignal,
): Promise<ProductContentV1> {
  return getJson<ProductContentV1>(
    `/api/v1/products/${encodeURIComponent(productId)}/content?maximum_points=192`,
    signal,
  );
}
