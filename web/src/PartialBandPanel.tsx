import { useEffect, useState } from "react";

type Artifact = {name: string; sha256: string; byte_count: number};
type Status = {
  state: "not_started" | "partial" | "figures_ready";
  completed_visits: number;
  manifest: null | {probe_count: number; candidate_probe_count: number; artifacts: Artifact[]};
};

export function PartialBandPanel({sessionId, inputDigest}: {sessionId: string; inputDigest: string}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}/partial-band`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true; let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch(`${base}?input_manifest_sha256=${encodeURIComponent(inputDigest)}`, {signal: controller.signal});
        if (!response.ok) throw new Error(`Partial-band analysis unavailable (${response.status})`);
        const value = await response.json() as Status;
        if (active) { setStatus(value); setError(null); }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "Partial-band evidence unavailable");
      } finally { busy = false; }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [base, inputDigest]);
  const url = (a: Artifact) => `${base}/${a.name}?input_manifest_sha256=${encodeURIComponent(inputDigest)}&artifact_sha256=${encodeURIComponent(a.sha256)}`;
  return <section className="scanner-results-panel adaptive-analysis" aria-label="Native low-rate analysis">
    <h3>Native 1.25 MS/s · partial-band GLRT64</h3>
    <p>Experimental candidate-only analysis. Non-overlapping 20 ms probes cover every retained dwell on both receivers.
      Confirmation uses seeded, disjoint whole-frame groups. Receiver filtering is an approximate model.</p>
    {error ? <p role="alert">{error}</p> : !status ? <p role="status">Loading analysis…</p> : <>
      <p role="status">{status.state === "figures_ready" ? "Figures ready" : status.state === "partial" ? "Partial checkpoints" : "Analysis not started"} · {status.completed_visits} checkpointed dwells</p>
      {status.manifest ? <p>{status.manifest.probe_count} analyzed probes · {status.manifest.candidate_probe_count} probes passed candidate gates.</p> : null}
      {status.manifest?.artifacts.map(a => a.name.endsWith(".png") ? <figure key={a.sha256} className="adaptive-analysis-figure">
        <figcaption>{a.name.replace(".png", "").replaceAll("-", " ")}</figcaption>
        <a href={url(a)} target="_blank" rel="noreferrer"><img src={url(a)} alt={`Partial-band ${a.name}`} loading="lazy" /></a>
      </figure> : <p key={a.sha256}><a href={url(a)} download={a.name}>Download {a.name}</a></p>)}
    </>}
    <p>CFO associations are not satellite identities. Dual-RX phase and position inference are not qualified for this partial-band model.</p>
  </section>;
}
