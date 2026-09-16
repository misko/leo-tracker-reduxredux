import { useEffect, useState } from "react";
import type { AdaptiveCapture } from "./adaptive-api";
import { adaptiveFigureUrl, getAdaptiveAnalysis } from "./adaptive-analysis-api";
import type { AdaptiveAnalysisStatus, AdaptiveArtifact, AdaptiveFigure, AdaptiveProbeStride } from "./adaptive-analysis-api";
import { frozenAdaptivePhaseArtifact } from "./adaptive-phase-artifacts";
import type { FrozenAdaptivePhaseArtifact } from "./adaptive-phase-artifacts";

const figureCopy: Record<AdaptiveArtifact, { title: string; detail: string }> = {
  "coverage": { title: "Retained channel coverage", detail: "Actual valid intervals; empty time is not interpolated. An outlined marker is an incomplete hop start." },
  "glrt64-response": { title: "Fractional GLRT response", detail: "Strongest complete fractional candidate per receiver and probe. Incomplete estimates do not become negative detections." },
  "cfo-trajectories": { title: "CFO candidates and associations", detail: "All passed fractional CFO candidates. Dashed fits use the strongest candidate per visit/RX, separately by target. They do not identify satellites or join lower/upper or different channels. Marker opacity does not encode signal strength." },
};

const RADIO003A_SERIAL = "104000bac4950008230026001b440a003a";
const RECEIVER_INPUT_RCA = "/reports/radio003a-rx-input-rca.html";

function FigureView({ status, figure }: { status: AdaptiveAnalysisStatus; figure: AdaptiveFigure }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const url = adaptiveFigureUrl(status, figure);
  const copy = figureCopy[figure.name];
  return <figure className="adaptive-analysis-figure">
    <figcaption><h4>{copy.title}</h4><p>{copy.detail}</p></figcaption>
    {failed ? <p role="alert">This figure could not be loaded or its published evidence is unavailable.</p> : <>
      {!loaded ? <p role="status">Loading {copy.title.toLowerCase()}…</p> : null}
      <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${copy.title.toLowerCase()} PNG`}>
        <img src={url} alt={copy.title} loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
      </a>
    </>}
  </figure>;
}

function FrozenPhaseFigure({ artifact }: { artifact: FrozenAdaptivePhaseArtifact }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const title = "GLRT tracks with dual-RX phase progression";
  return <figure
    className="adaptive-analysis-figure adaptive-phase-replay"
    data-artifact-sha256={artifact.sha256}
    data-artifact-bytes={artifact.byteCount}
  >
    <figcaption>
      <h4>{title}</h4>
      <p>Frozen historical replay for this exact recording. Gray marks are passed RX0 GLRT candidates; phase-colored connectors pair simultaneous two-signal tracks. Diamonds and the lower panels show phase-blind associations and wrapped/unwrapped receiver-phase double differences. Lines stop at unresolved gaps.</p>
      <p>This replay is supplemental evidence, not part of the live detector decision and not inferred for recordings without a published artifact.</p>
    </figcaption>
    {failed ? <p role="alert">The published dual-RX phase replay could not be loaded.</p> : <>
      {!loaded ? <p role="status">Loading dual-RX phase replay…</p> : null}
      <a href={artifact.href} target="_blank" rel="noreferrer" aria-label={`Open ${title.toLowerCase()} PNG`}>
        <img src={artifact.href} alt={title} loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
      </a>
    </>}
  </figure>;
}

export function AdaptiveAnalysisPanel({ capture }: { capture: AdaptiveCapture }) {
  const [probeStrideMs, setProbeStrideMs] = useState<AdaptiveProbeStride>(120);
  const [status, setStatus] = useState<AdaptiveAnalysisStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const phaseArtifact = capture.schema_version === 1
    ? frozenAdaptivePhaseArtifact(capture.session_id)
    : null;
  useEffect(() => {
    let active = true; let busy = false;
    const controller = new AbortController();
    setStatus(null); setLoading(true); setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await getAdaptiveAnalysis(capture, controller.signal, probeStrideMs);
        if (active) { setStatus(result); setError(null); }
      } catch (failure) {
        if (active) { setStatus(null); setError(failure instanceof Error ? failure.message : "Adaptive analysis is unavailable"); }
      } finally { busy = false; if (active) setLoading(false); }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [capture.session_id, capture.input_manifest_sha256, capture.retained_visits, capture.sample_rate_hz, probeStrideMs]);
  const label = status?.state === "figures_ready" ? "Figures ready" : status?.state === "metrics_complete" ? "Metrics published"
    : status?.state === "partial" ? "Partial checkpoints" : "Not started";
  return <section className="scanner-results-panel adaptive-analysis" aria-label="Adaptive fractional analysis">
    <header><h3>Fractional GLRT and Doppler analysis</h3><strong>{loading ? "Loading…" : error || !status ? "Unavailable" : label}</strong></header>
    <label>Analysis sampling <select value={probeStrideMs} onChange={event => setProbeStrideMs(Number(event.target.value) as AdaptiveProbeStride)}>
      <option value={120}>Automatic overview · one probe per dwell</option>
      <option value={10}>Dense analysis · 10 ms stride (if published)</option>
    </select></label>
    <p>{probeStrideMs === 120 ? `Automatic overview uses one 20 ms probe per 120 ms retained dwell, on ${capture.schema_version !== 1 ? `RX${capture.physical_receiver} at native ${capture.sample_rate_hz / 1e6} MS/s` : "both receivers"}. It does not analyze every sample; full recorded IQ is retained.` : "Dense analysis uses overlapping 20 ms probes every 10 ms. It is a separate, more expensive analysis and is not scheduled automatically."}</p>
    {capture.schema_version !== 1 && capture.radio_serial === RADIO003A_SERIAL ? <aside className={`adaptive-input-note ${capture.physical_receiver === 1 ? "adaptive-input-note-warning" : ""}`} aria-label="Receiver input status">
      <strong>{capture.physical_receiver === 1 ? "RX1 has no connected antenna feed at this installation." : "RX0 is the connected antenna input at this installation."}</strong>
      <p>{capture.physical_receiver === 1
        ? "A capture can have healthy source-counter duty while containing almost only receiver noise. Sparse GLRT and CFO results on this RX1 recording do not indicate a 10 MS/s transport failure."
        : "Saved controls show that native 10 MS/s and decimated 2.5 MS/s detection both work when signal is present on RX0."}</p>
      <a href={RECEIVER_INPUT_RCA} target="_blank" rel="noreferrer">Read the RX0/RX1 detection root-cause analysis</a>
    </aside> : null}
    {error ? <p role="alert">{error}. Recording and on-radio evidence remain separate.</p> : null}
    {!loading && !error && !status ? <p>Analysis presentation is unavailable for this capture on this server. It is not queued here.</p> : null}
    {status ? <>
      <p>{status.checkpoint_visits} / {status.total_visits} retained visits have saved checkpoints · 20 ms probes / {status.configuration.probe_stride_ms} ms stride · {capture.schema_version !== 1 ? `RX${capture.physical_receiver} analyzed offline at ${capture.sample_rate_hz / 1e6} MS/s` : "both recorded receivers analyzed offline"}</p>
      {status.total_visits > 0 ? <progress aria-label="Saved adaptive analysis checkpoints" value={status.checkpoint_visits} max={status.total_visits} /> : <p>No complete dwell was retained in this capture.</p>}
      {status.state === "not_started" ? <p>No checkpoint has been published for this sampling policy. Opening this view does not start or queue analysis.</p> : null}
      {status.state === "partial" ? <p>This count reflects published checkpoint files. Their full numerical contents are verified when metrics are finalized; figures are not ready.</p> : null}
      {status.state === "metrics_complete" ? <p>All retained visits have a sealed metrics manifest. Overview figures have not been published yet.</p> : null}
      <p>This is a saved-progress snapshot, not a live-worker status. Capture duty and radio-side detector health are shown independently.</p>
      {status.overview ? <>
        <p>{status.overview.association_count} candidate associations from {status.overview.selected_observation_count} strongest-per-visit observations.</p>
        {status.overview.truncated_association_count > 0 ? <p role="status">{status.overview.truncated_association_count} association hypotheses exceeded the configured output bound. All passed CFO candidates remain in the scatter plot.</p> : null}
        {status.overview.artifacts.map(figure => <FigureView key={`${status.binding_sha256}:${figure.name}:${figure.sha256}`} status={status} figure={figure} />)}
      </> : null}
      {phaseArtifact ? <FrozenPhaseFigure artifact={phaseArtifact} /> : null}
    </> : null}
    {!status && phaseArtifact ? <FrozenPhaseFigure artifact={phaseArtifact} /> : null}
  </section>;
}
