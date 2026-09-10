import type { AdaptiveCapture } from "./adaptive-api";

export const adaptiveArtifacts = ["coverage", "glrt64-response", "cfo-trajectories"] as const;
export type AdaptiveArtifact = typeof adaptiveArtifacts[number];
export type AdaptiveProbeStride = 10 | 120;
export interface AdaptiveFigure {
  name: AdaptiveArtifact; content_type: "image/png"; sha256: string; byte_count: number;
}
export interface AdaptiveAnalysisStatus {
  schema_version: 1; kind: "adaptive_hop_analysis_status";
  session_id: string; input_manifest_sha256: string; binding_sha256: string;
  configuration: {
    schema_version: 1; analyzer_id: "adaptive-hop-fractional-glrt64-cfo-v1";
    sample_rate_hz: 2500000 | 5000000; valid_visit_ms: 120; probe_ms: 20;
    probe_stride_ms: number; glrt64_margin_gate: number; maximum_acquisition_candidates: number;
    receiver_ids: [0, 1]; timing_refinement: "circular-five-cell-log-parabola-plus-lanczos16-v1";
    decision_score: "fractional-epoch-conditioned-glrt64-v1";
  };
  total_visits: number; checkpoint_visits: number;
  state: "not_started" | "partial" | "metrics_complete" | "figures_ready";
  progress_basis: "no_checkpoints" | "file_inventory" | "sealed_metrics_manifest";
  worker_activity: "not_observed"; metrics_manifest_sha256: string | null;
  overview: null | {
    schema_version: 1; kind: "adaptive_hop_fractional_overview";
    presentation_id: "adaptive-actual-visit-glrt64-overview-v1";
    session_id: string; binding_sha256: string; metrics_manifest_sha256: string;
    finalized_utc_ns: string; artifacts: AdaptiveFigure[];
    trajectory_configuration_sha256: string;
    trajectory_input_policy: "strongest-passed-fractional-candidate-per-visit-rx";
    trajectory_scope: "separate-target-and-receiver-candidate-associations";
    selected_observation_count: number; association_count: number; truncated_association_count: number;
  };
}

const digest = (v: unknown): v is string => typeof v === "string" && /^sha256:[0-9a-f]{64}$/.test(v);
const count = (v: unknown, maximum: number): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && v <= maximum;
const u64 = (v: unknown): v is string => typeof v === "string" && /^(0|[1-9][0-9]{0,19})$/.test(v) && BigInt(v) < 18446744073709551616n;

export async function getAdaptiveAnalysis(capture: AdaptiveCapture, signal?: AbortSignal, probeStrideMs: AdaptiveProbeStride = 120): Promise<AdaptiveAnalysisStatus | null> {
  const response = await fetch(`/api/v1/scanner/adaptive-sessions/${encodeURIComponent(capture.session_id)}/analysis?probe_stride_ms=${probeStrideMs}`, { signal, cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Adaptive analysis request failed (${response.status})`);
  const value = await response.json() as AdaptiveAnalysisStatus;
  const cfg = value?.configuration;
  if (!value || value.schema_version !== 1 || value.kind !== "adaptive_hop_analysis_status"
      || value.session_id !== capture.session_id || value.input_manifest_sha256 !== capture.input_manifest_sha256
      || !digest(value.binding_sha256) || !cfg || cfg.schema_version !== 1
      || cfg.analyzer_id !== "adaptive-hop-fractional-glrt64-cfo-v1" || cfg.sample_rate_hz !== capture.sample_rate_hz
      || cfg.valid_visit_ms !== 120 || cfg.probe_ms !== 20 || cfg.probe_stride_ms !== probeStrideMs
      || !Number.isFinite(cfg.glrt64_margin_gate) || cfg.glrt64_margin_gate <= 0
      || !count(cfg.maximum_acquisition_candidates, 16) || cfg.maximum_acquisition_candidates < 1
      || !Array.isArray(cfg.receiver_ids) || cfg.receiver_ids.length !== 2 || cfg.receiver_ids[0] !== 0 || cfg.receiver_ids[1] !== 1
      || cfg.timing_refinement !== "circular-five-cell-log-parabola-plus-lanczos16-v1"
      || cfg.decision_score !== "fractional-epoch-conditioned-glrt64-v1"
      || !count(value.total_visits, 2500) || value.total_visits !== capture.retained_visits
      || !count(value.checkpoint_visits, value.total_visits) || value.worker_activity !== "not_observed"
      || !["not_started", "partial", "metrics_complete", "figures_ready"].includes(value.state)) {
    throw new Error("Adaptive analysis source or configuration is invalid");
  }
  const complete = value.state === "metrics_complete" || value.state === "figures_ready";
  if ((complete ? !digest(value.metrics_manifest_sha256) || value.checkpoint_visits !== value.total_visits : value.metrics_manifest_sha256 !== null)
      || (value.state === "not_started" && value.checkpoint_visits !== 0)
      || (value.state === "figures_ready") !== (value.overview !== null)
      || value.progress_basis !== (complete ? "sealed_metrics_manifest" : value.state === "not_started" ? "no_checkpoints" : "file_inventory")) {
    throw new Error("Adaptive analysis progress contradicts published evidence");
  }
  const overview = value.overview;
  if (overview !== null && (!overview || overview.schema_version !== 1 || overview.kind !== "adaptive_hop_fractional_overview"
      || overview.presentation_id !== "adaptive-actual-visit-glrt64-overview-v1"
      || overview.session_id !== value.session_id || overview.binding_sha256 !== value.binding_sha256
      || overview.metrics_manifest_sha256 !== value.metrics_manifest_sha256 || !u64(overview.finalized_utc_ns)
      || !digest(overview.trajectory_configuration_sha256)
      || overview.trajectory_input_policy !== "strongest-passed-fractional-candidate-per-visit-rx"
      || overview.trajectory_scope !== "separate-target-and-receiver-candidate-associations"
      || !count(overview.selected_observation_count, value.total_visits * 2)
      || !count(overview.association_count, 1024) || !count(overview.truncated_association_count, Number.MAX_SAFE_INTEGER)
      || !Array.isArray(overview.artifacts) || overview.artifacts.length !== 3
      || overview.artifacts.some((a, i) => !a || a.name !== adaptiveArtifacts[i] || a.content_type !== "image/png"
        || !digest(a.sha256) || !count(a.byte_count, 16 * 1024 * 1024) || a.byte_count === 0))) {
    throw new Error("Adaptive figures are not bound to these metrics");
  }
  return value;
}

export function adaptiveFigureUrl(status: AdaptiveAnalysisStatus, figure: AdaptiveFigure): string {
  const query = new URLSearchParams({ probe_stride_ms: String(status.configuration.probe_stride_ms), binding_sha256: status.binding_sha256, artifact_sha256: figure.sha256 });
  return `/api/v1/scanner/adaptive-sessions/${encodeURIComponent(status.session_id)}/analysis/${figure.name}.png?${query.toString()}`;
}
