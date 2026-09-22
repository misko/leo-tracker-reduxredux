import { useEffect, useState } from "react";

type Artifact = { name: "relative-phase-overview" | "relative-phase-dwells"; sha256: string; byte_count: number };
type Status = {
  schema_version: 1; session_id: string; input_manifest_sha256: string; binding_sha256: string;
  state: "pending" | "ready" | "insufficient_signal" | "not_applicable";
  manifest: null | { binding_sha256: string; total_visit_count: number; selected_visits: number[];
    supported_visit_count: number; pilot_checked_visit_count: number; geometric_phase_claimed: false;
    phase_continuity_across_retunes: false; artifacts: Artifact[] };
};

export function parseRelativePhase(value: unknown, sessionId: string): Status {
  const s = value as Status;
  const digest = /^sha256:[0-9a-f]{64}$/;
  if (!s || s.schema_version !== 1 || s.session_id !== sessionId || !digest.test(s.binding_sha256)
    || !digest.test(s.input_manifest_sha256) || !["pending", "ready", "insufficient_signal", "not_applicable"].includes(s.state)
    || (s.state === "pending") !== (s.manifest === null)) throw new Error("Invalid relative phase status");
  const m = s.manifest;
  if (m && (m.binding_sha256 !== s.binding_sha256 || m.geometric_phase_claimed !== false || m.phase_continuity_across_retunes !== false
    || !Array.isArray(m.selected_visits) || m.selected_visits.length > 64 || !Array.isArray(m.artifacts) || m.artifacts.length !== 2
    || new Set(m.artifacts.map(a => a.name)).size !== 2
    || m.artifacts.some(a => !["relative-phase-overview", "relative-phase-dwells"].includes(a.name) || !digest.test(a.sha256) || !Number.isInteger(a.byte_count) || a.byte_count <= 0))) {
    throw new Error("Invalid relative phase manifest");
  }
  return s;
}

function PhaseImage({ url, title }: { url: string; title: string }) {
  const [failed, setFailed] = useState(false);
  return <figure className="adaptive-analysis-figure"><figcaption>{title}</figcaption>{failed ? <p role="alert">The relative phase PNG could not be loaded.</p>
    : <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={title} loading="lazy" onError={() => setFailed(true)} /></a>}</figure>;
}

export function AdaptiveRelativePhase({ sessionId }: { sessionId: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController(); let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const response = await fetch(`/api/v1/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}/analysis/relative-phase`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error(`Relative phase request failed (${response.status})`);
        const result = parseRelativePhase(await response.json(), sessionId);
        if (!controller.signal.aborted) { setStatus(result); setError(null); }
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Relative phase unavailable"); }
      finally { busy = false; }
    };
    void refresh(); const timer = window.setInterval(() => void refresh(), 15000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [sessionId]);
  const m = status?.manifest;
  return <section aria-label="Broadband and pilot relative phase">
    <h3>Broadband and pilot relative phase</h3>
    <p>Receiver-to-receiver phase within each dwell. Separate references across retunes; this is not calibrated geometric phase.</p>
    {error ? <p role="alert">{error}</p> : null}
    {!status && !error ? <p>Loading relative phase…</p> : null}
    {status?.state === "pending" ? <p>Relative phase analysis is queued or running.</p> : null}
    {status?.state === "not_applicable" ? <p>Requires simultaneous RX0/RX1 recordings.</p> : null}
    {status?.state === "insufficient_signal" ? <p>No selected dwell passed the broadband phase checks.</p> : null}
    {m ? <><p>{m.selected_visits.length} selected / {m.total_visit_count} recorded dwells · {m.supported_visit_count} broadband-supported · {m.pilot_checked_visit_count} with later pilot comparisons. Selection is limited to the 64 strongest paired GLRT dwells; figures show up to 12 representatives.</p>
      {m.artifacts.map(a => {
        const query = new URLSearchParams({ binding_sha256: status.binding_sha256, artifact_sha256: a.sha256 });
        const url = `/api/v1/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}/analysis/relative-phase/${a.name}.png?${query}`;
        return <PhaseImage key={a.sha256} url={url} title={a.name === "relative-phase-overview" ? "Relative phase quality and pilot agreement" : "Within-dwell phase trajectories and matched pilots"} />;
      })}</> : null}
  </section>;
}
