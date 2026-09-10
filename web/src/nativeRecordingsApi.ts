export interface NativeRecordingSummary {
  bundle_id: string;
  serial: string;
  boot_id: string;
  fit_sha256: string;
  visit: number;
  epoch: number;
  episode_index: number;
  runtime_result: number;
  owner_status: string;
  source_rate_hz: 60000000;
  pilot_samples: 79200;
  head_count: number;
  supported_count: number;
  rejected_count: number;
  observed_start_span_s: number | null;
  supported_cfo_min_hz: number | null;
  supported_cfo_max_hz: number | null;
  frequency_reference: "receiver_relative_uncalibrated";
  evidence_mode: "retrospective_retained_owner_correspondence";
  acquisition_verified: false;
  original_native_iq_verified: false;
  physical_precision_qualified: false;
}

export interface NativeRecordingEntry {
  bundle_id: string;
  summary: NativeRecordingSummary | null;
  error: "integrity_unavailable" | null;
}

export interface NativeRecordingList {
  schema_version: 1;
  total: number;
  next_cursor: number | null;
  items: NativeRecordingEntry[];
}

export interface NativeRecordingRow {
  measurement: {
    sequence: number;
    frame: number;
    native_start_sample: string;
    delay_s: number;
    cfo_hz: number;
    coherence: number;
    supported: boolean;
    rejection: number;
    hardware_fault: number;
  };
  coarse_relative_scheduled_start_s: number;
  coarse_relative_refined_start_s: number;
}

export interface NativeRecordingDetail {
  schema_version: 1;
  summary: NativeRecordingSummary;
  cursor: number;
  next_cursor: number | null;
  rows: NativeRecordingRow[];
}

async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "GET", signal });
  if (!response.ok) {
    const message = response.status === 409
      ? "Recording integrity check failed. Its measurements are unavailable."
      : `Native recording request failed (${response.status}).`;
    throw new Error(message);
  }
  return await response.json() as T;
}

export function getNativeRecordings(cursor: number, signal?: AbortSignal) {
  return read<NativeRecordingList>(`/api/v1/native-recordings?cursor=${cursor}&limit=20`, signal);
}

export function getNativeRecording(id: string, cursor: number, signal?: AbortSignal) {
  return read<NativeRecordingDetail>(
    `/api/v1/native-recordings/${encodeURIComponent(id)}?cursor=${cursor}&limit=200`, signal,
  );
}
