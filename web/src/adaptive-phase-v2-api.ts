import type { AdaptiveCapture } from "./adaptive-api";

export interface AdaptivePhaseV2Figure {
  name: "dual-rx-double-difference-time"; content_type: "image/png"; sha256: string; byte_count: number;
}
export interface AdaptivePhaseV2Manifest {
  schema_version: 2; kind: "adaptive_dual_rx_phase_manifest";
  analysis_id: "adaptive-qin-pilot-double-difference-v2";
  session_id: string; input_manifest_sha256: string; glrt_binding_sha256: string;
  glrt_metrics_manifest_sha256: string; state: "ready" | "insufficient_signal";
  reason: "published_phase_time_hypotheses" | "no_qualified_double_difference";
  total_visit_count: number; checkpoint_visit_count: number; qualified_visit_count: number;
  hypothesis_count: number; geometry_phase_state: "unavailable" | "ambiguous" | "conditionally_unique";
  geometry_phase_reason: string; receiver_product: "rx1_times_conjugate_rx0";
  phase_continuity_across_retunes: false; association_uses_phase: false; aliases_resolved: false;
  artifact: AdaptivePhaseV2Figure | null; finalized_utc_ns: string;
}
export interface AdaptivePhaseV2Status {
  schema_version: 2; kind: "adaptive_dual_rx_phase_status"; session_id: string;
  input_manifest_sha256: string; receiver_ids: number[];
  state: "pending" | "ready" | "insufficient_signal" | "not_applicable";
  reason: "awaiting_phase_analysis" | "published_phase_time_hypotheses" | "no_qualified_double_difference" | "requires_simultaneous_rx0_rx1";
  checkpoint_visit_count: number; total_visit_count: number; worker_activity: "not_observed";
  manifest: AdaptivePhaseV2Manifest | null;
}

const digest = (value: unknown): value is string => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
const count = (value: unknown, maximum: number): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

export async function getAdaptivePhaseV2(capture: AdaptiveCapture, signal?: AbortSignal, probeStrideMs = 120): Promise<AdaptivePhaseV2Status | null> {
  const routeVersion = capture.schema_version === 4 ? 3 : capture.schema_version;
  const response = await fetch(`/api/v${routeVersion}/scanner/adaptive-sessions/${encodeURIComponent(capture.session_id)}/analysis/dual-rx-phase-v2?probe_stride_ms=${probeStrideMs}`, { signal, cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Adaptive phase V2 request failed (${response.status})`);
  const value = await response.json() as AdaptivePhaseV2Status;
  const receivers = capture.schema_version === 2 || capture.schema_version === 3 ? [capture.physical_receiver] : [0, 1];
  if (!value || value.schema_version !== 2 || value.kind !== "adaptive_dual_rx_phase_status"
      || value.session_id !== capture.session_id || value.input_manifest_sha256 !== capture.input_manifest_sha256
      || value.worker_activity !== "not_observed" || !count(value.checkpoint_visit_count, 5000)
      || !count(value.total_visit_count, 5000) || value.checkpoint_visit_count > value.total_visit_count
      || !Array.isArray(value.receiver_ids) || value.receiver_ids.length !== receivers.length
      || value.receiver_ids.some((rx, index) => rx !== receivers[index])) throw new Error("Adaptive phase V2 status is invalid");
  const expectedReason = { pending: "awaiting_phase_analysis", ready: "published_phase_time_hypotheses", insufficient_signal: "no_qualified_double_difference", not_applicable: "requires_simultaneous_rx0_rx1" }[value.state];
  const published = value.state === "ready" || value.state === "insufficient_signal";
  if (value.reason !== expectedReason || published !== (value.manifest !== null)
      || (value.state === "not_applicable") !== (receivers.length !== 2)) throw new Error("Adaptive phase V2 state contradicts its source");
  const manifest = value.manifest;
  const artifact = manifest?.artifact;
  const artifactInvalid = artifact !== null && artifact !== undefined
    && (artifact.name !== "dual-rx-double-difference-time" || artifact.content_type !== "image/png"
      || !digest(artifact.sha256) || !count(artifact.byte_count, 16 * 1024 * 1024)
      || artifact.byte_count === 0);
  if (manifest && (manifest.schema_version !== 2
      || manifest.analysis_id !== "adaptive-qin-pilot-double-difference-v2"
      || manifest.session_id !== value.session_id || manifest.input_manifest_sha256 !== value.input_manifest_sha256
      || !digest(manifest.glrt_binding_sha256) || !digest(manifest.glrt_metrics_manifest_sha256)
      || manifest.association_uses_phase !== false || manifest.aliases_resolved !== false
      || manifest.phase_continuity_across_retunes !== false || manifest.receiver_product !== "rx1_times_conjugate_rx0"
      || manifest.state !== value.state || !count(manifest.hypothesis_count, 70000)
      || (manifest.state === "ready") !== (manifest.artifact !== null)
      || artifactInvalid)) throw new Error("Adaptive phase V2 manifest is invalid");
  return value;
}

export function adaptivePhaseV2FigureUrl(status: AdaptivePhaseV2Status, probeStrideMs: number): string {
  const manifest = status.manifest;
  if (!manifest?.artifact) throw new Error("Adaptive phase V2 figure is unpublished");
  const query = new URLSearchParams({ probe_stride_ms: String(probeStrideMs), glrt_binding_sha256: manifest.glrt_binding_sha256, artifact_sha256: manifest.artifact.sha256 });
  return `/api/v1/scanner/adaptive-sessions/${encodeURIComponent(status.session_id)}/analysis/dual-rx-phase-v2/artifact.png?${query.toString()}`;
}
