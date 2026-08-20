import type {
  ProductContentV1,
  ActiveQueueV1,
  QualificationCampaignDetailV1,
  QualificationCampaignListV1,
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

export interface StandardReprocessResultV1 {
  schema_version: 1;
  session_id: string;
  run_id: string;
  pipeline_release_id: string;
  previous_current_run_id: string | null;
  queued_job_count: number;
  state: "queued";
}

export interface StandardControlStatusV1 {
  schema_version: 1;
  reprocess_enabled: boolean;
}

export function getQualificationCampaigns(
  cursor = 0,
  limit = 10,
  signal?: AbortSignal,
): Promise<QualificationCampaignListV1> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<QualificationCampaignListV1>(
    `/api/v1/qualification/campaigns?${params}`,
    signal,
  );
}

export function getQualificationCampaign(
  campaignId: string,
  signal?: AbortSignal,
): Promise<QualificationCampaignDetailV1> {
  return getJson<QualificationCampaignDetailV1>(
    `/api/v1/qualification/campaigns/${encodeURIComponent(campaignId)}`,
    signal,
  );
}

export function getStatus(signal?: AbortSignal): Promise<SystemStatusV1> {
  return getJson<SystemStatusV1>("/api/v1/status", signal);
}

export function getControlStatus(signal?: AbortSignal): Promise<StandardControlStatusV1> {
  return getJson<StandardControlStatusV1>("/api/v2/control/status", signal);
}

export function getActiveQueue(signal?: AbortSignal): Promise<ActiveQueueV1> {
  return getJson<ActiveQueueV1>("/api/v1/queue?limit=200", signal);
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

export function getProductContent(
  productId: string,
  signal?: AbortSignal,
): Promise<ProductContentV1> {
  return getJson<ProductContentV1>(
    `/api/v1/products/${encodeURIComponent(productId)}/content?maximum_points=192`,
    signal,
  );
}
