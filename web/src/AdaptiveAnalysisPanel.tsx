import { useEffect, useState } from "react";
import type { AdaptiveCapture } from "./adaptive-api";
import { adaptiveFigureUrl, getAdaptiveAnalysis } from "./adaptive-analysis-api";
import type { AdaptiveAnalysisStatus, AdaptiveArtifact, AdaptiveFigure } from "./adaptive-analysis-api";

const figureCopy: Record<AdaptiveArtifact, { title: string; detail: string }> = {
  "coverage": { title: "Retained channel coverage", detail: "Actual valid intervals; empty time is not interpolated. An outlined marker is an incomplete hop start." },
  "glrt64-response": { title: "Fractional GLRT response", detail: "Strongest complete fractional candidate per receiver and probe. Incomplete estimates do not become negative detections." },
  "cfo-trajectories": { title: "CFO candidates and associations", detail: "All passed fractional CFO candidates. Dashed fits use the strongest candidate per visit/RX, separately by target. They do not identify satellites or join lower/upper or different channels. Marker opacity does not encode signal strength." },
};

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

export function AdaptiveAnalysisPanel({ capture }: { capture: AdaptiveCapture }) {
  const [status, setStatus] = useState<AdaptiveAnalysisStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true; let busy = false;
    const controller = new AbortController();
    setStatus(null); setLoading(true); setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await getAdaptiveAnalysis(capture, controller.signal);
        if (active) { setStatus(result); setError(null); }
      } catch (failure) {
        if (active) { setStatus(null); setError(failure instanceof Error ? failure.message : "Adaptive analysis is unavailable"); }
      } finally { busy = false; if (active) setLoading(false); }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [capture.session_id, capture.input_manifest_sha256, capture.retained_visits, capture.sample_rate_hz]);
  const label = status?.state === "figures_ready" ? "Figures ready" : status?.state === "metrics_complete" ? "Metrics published"
    : status?.state === "partial" ? "Partial checkpoints" : "Not started";
  return <section className="scanner-results-panel adaptive-analysis" aria-label="Adaptive fractional analysis">
    <header><h3>Fractional GLRT and Doppler analysis</h3><strong>{loading ? "Loading…" : error || !status ? "Unavailable" : label}</strong></header>
    {error ? <p role="alert">{error}. Recording and on-radio evidence remain separate.</p> : null}
    {!loading && !error && !status ? <p>Analysis presentation is unavailable for this capture on this server. It is not queued here.</p> : null}
    {status ? <>
      <p>{status.checkpoint_visits} / {status.total_visits} retained visits have saved checkpoints · 20 ms probes / 10 ms stride · both recorded receivers analyzed offline</p>
      {status.total_visits > 0 ? <progress aria-label="Saved adaptive analysis checkpoints" value={status.checkpoint_visits} max={status.total_visits} /> : <p>No complete dwell was retained in this capture.</p>}
      {status.state === "not_started" ? <p>No dense analysis checkpoint has been published. Opening this view does not start or queue analysis.</p> : null}
      {status.state === "partial" ? <p>This count reflects published checkpoint files. Their full numerical contents are verified when metrics are finalized; figures are not ready.</p> : null}
      {status.state === "metrics_complete" ? <p>All retained visits have a sealed metrics manifest. Overview figures have not been published yet.</p> : null}
      <p>This is a saved-progress snapshot, not a live-worker status. Capture duty and radio-side detector health are shown independently.</p>
      {status.overview ? <>
        <p>{status.overview.association_count} candidate associations from {status.overview.selected_observation_count} strongest-per-visit observations.</p>
        {status.overview.truncated_association_count > 0 ? <p role="status">{status.overview.truncated_association_count} association hypotheses exceeded the configured output bound. All passed CFO candidates remain in the scatter plot.</p> : null}
        {status.overview.artifacts.map(figure => <FigureView key={`${status.binding_sha256}:${figure.name}:${figure.sha256}`} status={status} figure={figure} />)}
      </> : null}
    </> : null}
  </section>;
}
