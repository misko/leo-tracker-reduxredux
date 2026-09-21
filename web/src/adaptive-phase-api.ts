import type { AdaptiveCapture } from "./adaptive-api";

export interface AdaptivePhaseFigure {
  name: "dual-rx-phase-progression"; content_type: "image/png"; sha256: string; byte_count: number;
}
export interface AdaptivePhaseManifest {
  schema_version: 1; kind: "adaptive_dual_rx_phase_manifest";
  analysis_id: "adaptive-qin-pilot-double-difference-v1";
  session_id: string; input_manifest_sha256: string; glrt_binding_sha256: string;
  glrt_metrics_manifest_sha256: string; state: "ready" | "insufficient_signal";
  reason: "published_phase_evidence" | "no_qualified_double_difference";
  qualified_phase_count: number; association_count: number;
  artifact: AdaptivePhaseFigure | null; finalized_utc_ns: string;
}
export interface AdaptivePhaseStatus {
  schema_version: 1; kind: "adaptive_dual_rx_phase_status";
  session_id: string; input_manifest_sha256: string; receiver_ids: number[];
  state: "pending" | "ready" | "insufficient_signal" | "not_applicable";
  reason: "awaiting_phase_analysis" | "published_phase_evidence" | "no_qualified_double_difference" | "requires_simultaneous_rx0_rx1";
  worker_activity: "not_observed"; manifest: AdaptivePhaseManifest | null;
}

const digest = (value: unknown): value is string => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
const count = (value: unknown, maximum: number): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

export async function getAdaptivePhase(capture: AdaptiveCapture, signal?: AbortSignal, probeStrideMs = 120): Promise<AdaptivePhaseStatus | null> {
  const routeVersion = capture.schema_version === 4 ? 3 : capture.schema_version;
  const response = await fetch(`/api/v${routeVersion}/scanner/adaptive-sessions/${encodeURIComponent(capture.session_id)}/analysis/dual-rx-phase?probe_stride_ms=${probeStrideMs}`, { signal, cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Adaptive phase request failed (${response.status})`);
  const value = await response.json() as AdaptivePhaseStatus;
  const receivers = capture.schema_version === 2 || capture.schema_version === 3
    ? [capture.physical_receiver] : [0, 1];
  if (!value || value.schema_version !== 1 || value.kind !== "adaptive_dual_rx_phase_status"
      || value.session_id !== capture.session_id || value.input_manifest_sha256 !== capture.input_manifest_sha256
      || !Array.isArray(value.receiver_ids) || value.receiver_ids.length !== receivers.length || value.receiver_ids.some((rx, i) => rx !== receivers[i])
      || !["pending", "ready", "insufficient_signal", "not_applicable"].includes(value.state)
      || value.worker_activity !== "not_observed") throw new Error("Adaptive phase status is invalid");
  const expectedReason = { pending: "awaiting_phase_analysis", ready: "published_phase_evidence", insufficient_signal: "no_qualified_double_difference", not_applicable: "requires_simultaneous_rx0_rx1" }[value.state];
  const published = value.state === "ready" || value.state === "insufficient_signal";
  if (value.reason !== expectedReason || published !== (value.manifest !== null)
      || (value.state === "not_applicable") !== (receivers.length !== 2)) throw new Error("Adaptive phase state contradicts its source");
  const manifest = value.manifest;
  if (manifest && (manifest.schema_version !== 1 || manifest.kind !== "adaptive_dual_rx_phase_manifest"
      || manifest.analysis_id !== "adaptive-qin-pilot-double-difference-v1" || manifest.session_id !== value.session_id
      || manifest.input_manifest_sha256 !== value.input_manifest_sha256 || manifest.state !== value.state
      || !digest(manifest.glrt_binding_sha256) || !digest(manifest.glrt_metrics_manifest_sha256)
      || !count(manifest.qualified_phase_count, 5000) || !count(manifest.association_count, 1024)
      || (value.state === "ready") !== (manifest.artifact !== null)
      || (manifest.artifact !== null && (manifest.artifact.name !== "dual-rx-phase-progression" || manifest.artifact.content_type !== "image/png"
        || !digest(manifest.artifact.sha256) || !count(manifest.artifact.byte_count, 16 * 1024 * 1024) || manifest.artifact.byte_count === 0)))) {
    throw new Error("Adaptive phase manifest is invalid");
  }
  return value;
}

export function adaptivePhaseFigureUrl(status: AdaptivePhaseStatus, probeStrideMs: number): string {
  const manifest = status.manifest;
  if (!manifest?.artifact) throw new Error("Adaptive phase figure is unpublished");
  const query = new URLSearchParams({ probe_stride_ms: String(probeStrideMs), glrt_binding_sha256: manifest.glrt_binding_sha256, artifact_sha256: manifest.artifact.sha256 });
  return `/api/v1/scanner/adaptive-sessions/${encodeURIComponent(status.session_id)}/analysis/dual-rx-phase/artifact.png?${query.toString()}`;
}
