import { useEffect, useState } from "react";

type Artifact = "shift-recovery" | "probe-comparison";
type Status = {
  schema_version: 1;
  session_id: string;
  state: "not_started" | "partial" | "complete";
  manifest: null | {
    session_id: string;
    input_manifest_sha256: string;
    evidence_sha256: string;
    sample_rate_hz: number;
    scheduled_probes: number;
    completed_probes: number;
    failed_probes: number;
    artifacts: Array<{ name: Artifact; sha256: string; byte_count: number }>;
  };
};

export function ScannerRefinementPanel({ sessionId, inputDigest }: {
  sessionId: string;
  inputDigest?: string;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<Artifact>("shift-recovery");
  const base = `/api/v1/scanner/refinement-comparisons/${encodeURIComponent(sessionId)}`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let busy = false;
    setStatus(null); setError(null); setArtifact("shift-recovery");
    const load = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch(base, { signal: controller.signal });
        if (response.status === 404) {
          if (active) setStatus({ schema_version: 1, session_id: sessionId, state: "not_started", manifest: null });
          return;
        }
        if (!response.ok) throw new Error(`Comparison evidence unavailable (${response.status})`);
        const value = await response.json() as Status;
        const m = value.manifest;
        if (value.schema_version !== 1 || value.session_id !== sessionId ||
            !["not_started", "partial", "complete"].includes(value.state) ||
            (value.state === "complete") !== (m !== null) ||
            (m !== null && (m.session_id !== sessionId ||
              (inputDigest !== undefined && inputDigest !== m.input_manifest_sha256) ||
              !Array.isArray(m.artifacts) || m.artifacts.length !== 2 ||
              m.artifacts[0].name !== "shift-recovery" || m.artifacts[1].name !== "probe-comparison"))) {
          throw new Error("Comparison evidence does not match this capture");
        }
        if (active) { setStatus(value); setError(null); }
      } catch (reason) {
        if (active && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason));
      } finally { busy = false; }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [base, sessionId, inputDigest]);
  const m = status?.manifest;
  return <section className="scanner-artifact-panel" aria-label="Local and joint GLRT comparison">
    <header><div><span>STORED-IQ COMPARISON</span><h3>Local and joint refinement</h3></div></header>
    <p>Known frequency and timing shifts test 512, 8192, local frequency refinement and joint timing/CFO iteration on this capture. Lower error is better; regressions and frequency-alias jumps are retained.</p>
    {error ? <p role="alert">{error}</p> : !m ? <p role="status">{status?.state === "partial"
      ? "Comparison checkpoints are saved; PNGs will appear after publication."
      : "Comparison PNGs have not been published yet."}</p> : <>
      <div className="scanner-artifact-tabs" role="tablist" aria-label="Refinement comparison figures">
        <button type="button" role="tab" aria-selected={artifact === "shift-recovery"} onClick={() => { setArtifact("shift-recovery"); setError(null); }}>Shift-recovery RMS</button>
        <button type="button" role="tab" aria-selected={artifact === "probe-comparison"} onClick={() => { setArtifact("probe-comparison"); setError(null); }}>Individual probe errors</button>
      </div>
      <div className="scanner-artifact-viewport">
        <img loading="lazy" src={`${base}/${artifact}.png?evidence=${encodeURIComponent(m.evidence_sha256)}`}
          alt={artifact === "shift-recovery" ? "GLRT settings compared using known shift recovery" : "Individual raw timing and frequency errors including alias jumps"}
          onError={() => setError("The comparison PNG could not be loaded")} />
      </div>
      <p>{m.completed_probes} of {m.scheduled_probes} bounded probes evaluated · {m.failed_probes} probe failures · {m.sample_rate_hz / 1e6} MS/s.</p>
      <p><a href={`${base}/${artifact}.png`}>Open comparison PNG</a> · <a href={`${base}/evidence.json`}>Download numerical evidence</a></p>
    </>}
    <p className="scanner-artifact-caption">Relative shift consistency, not absolute timing or Doppler accuracy. These experimental comparisons do not change scanner detection or hopping decisions.</p>
    <a href="https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_09_11_glrt_refinement_prototype/README.md">Read the historical 2.5 / 5 MS/s study</a>
  </section>;
}
