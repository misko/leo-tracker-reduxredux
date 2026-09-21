import { useEffect, useState } from "react";

type Product = {
  session_id: string; input_manifest_sha256: string; sample_rate_hz: number;
  trajectory_time_basis?: "qualified-utc" | "device-counter-relative";
  trajectory_state: string; tle_state: string; reasons: string[];
  physical_group_count: number; eligible_group_count: number; attempted_group_count: number;
  deferred_group_count: number;
  catalogue_exclusions: Array<{ catalog_number: number; name: string; reason: string }>;
  unscored_groups: Array<{ physical_group_id: string; reason: string }>;
  tle_candidates: Array<{ physical_group_id: string; leading_catalog_number: number | null;
    support_span_s: number; abstention_recommended: boolean; abstention_reasons: string[];
    leading_candidate_persisted_on_heldout?: boolean;
    heldout_runner_negative_log_score_margin?: number | null }>;
  position_diagnostic?: {
    state: "insufficient" | "diagnostic" | "failed";
    conditional_on_site_assisted_identity: true; position_fix_claimed: false;
    source_count: number; track_count: number; fit_observation_count: number;
    evaluation_observation_count: number; candidate_latitude_deg: number | null;
    candidate_longitude_deg: number | null; training_rms_hz: number | null;
    evaluation_rms_hz: number | null; jacobian_rank: number | null;
    condition_number: number | null; boundary_hit: boolean | null;
    reasons: string[]; runtime_ms: number;
  };
  artifacts: Array<{
    name: "trajectory" | "trajectory-tle" | "position-diagnostic" | `tle-review-${string}`;
    sha256: string;
  }>;
};
type Status = { session_id: string; state: string; phase: string; failure_summary: string | null; product: Product | null };

function artifactCaption(name: Product["artifacts"][number]["name"]): string {
  if (name === "trajectory") return "Measured trajectories";
  if (name === "trajectory-tle") return "TLE comparison";
  if (name === "position-diagnostic") return "Bounded position diagnostic";
  return `Per-track TLE review ${Number(name.slice("tle-review-".length))}`;
}

export function ScannerTrackingPanel({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/scanner/tracking/${encodeURIComponent(sessionId)}`;
  useEffect(() => {
    const controller = new AbortController(); let active = true; let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const response = await fetch(base, { signal: controller.signal });
        if (!response.ok) throw new Error(`Tracking unavailable (${response.status})`);
        const value = await response.json() as Status;
        if (value.session_id !== sessionId || (value.product &&
          (value.product.session_id !== sessionId || (inputDigest && value.product.input_manifest_sha256 !== inputDigest))))
          throw new Error("Tracking evidence does not match this capture");
        if (active) { setStatus(value); setError(null); }
      } catch (e) { if (active && !controller.signal.aborted) setError(String(e)); }
      finally { busy = false; }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [base, sessionId, inputDigest]);
  const p = status?.product;
  return <section className="scanner-artifact-panel" aria-label="Shared satellite trajectory tracking">
    <header><div><span>TRAJECTORY AND CATALOGUE EVIDENCE</span><h3>Cross-channel Doppler trajectories</h3></div>
      <small>{p ? `${p.sample_rate_hz / 1e6} MS/s · trajectories: ${p.trajectory_state} · TLE: ${p.tle_state}` : status?.phase ?? "Loading tracking status…"}</small></header>
    {error && <p role="alert">{error}</p>}
    {status?.failure_summary && <p role="alert">{status.failure_summary}</p>}
    {!p && !error && <p>Tracking will run automatically after scan analysis completes.</p>}
    {p && <>
      <p>{p.eligible_group_count} eligible of {p.physical_group_count} groups across hypotheses · {p.attempted_group_count} comparisons attempted · {p.deferred_group_count} deferred.</p>
      {p.tle_state === "pending" && <p>Measured trajectories are available; catalogue comparisons are still processing.</p>}
      {p.trajectory_state === "complete" && p.tle_state === "unavailable" &&
        (p.trajectory_time_basis === "device-counter-relative" ||
          p.reasons.some(reason => reason.includes("qualified absolute UTC"))) &&
        <p>Relative trajectories are available; catalogue comparison requires qualified absolute UTC.</p>}
      {p.tle_state === "no-eligible-groups" && <p>No group has the required 20 observations spanning at least 20 seconds.</p>}
      {p.reasons.map((reason, i) => <p key={i}>{reason}</p>)}
      {p.unscored_groups.map(g => <p key={g.physical_group_id}>Unscored group: {g.reason}</p>)}
      {p.catalogue_exclusions.length > 0 && <details><summary>{p.catalogue_exclusions.length} catalogue-labelled debris objects excluded before matching</summary>
        <ul>{p.catalogue_exclusions.map(c => <li key={c.catalog_number}>NORAD {c.catalog_number} · {c.name}</li>)}</ul></details>}
      {p.tle_candidates.length > 0 && <table className="scanner-table" aria-label="Shared TLE diagnostics"><thead><tr><th>Candidate</th><th>Support</th><th>Randomized evaluation</th><th>Disposition</th></tr></thead>
        <tbody>{p.tle_candidates.map(c => <tr key={c.physical_group_id}><td>{c.leading_catalog_number === null ? "Restricted null" : `NORAD ${c.leading_catalog_number}`}</td>
          <td>{c.support_span_s.toFixed(1)} s</td>
          <td>{c.leading_candidate_persisted_on_heldout === undefined ? "—" : c.leading_candidate_persisted_on_heldout
            ? `Leader retained${c.heldout_runner_negative_log_score_margin == null ? "" : ` · runner +${c.heldout_runner_negative_log_score_margin.toFixed(3)} NLL`}`
            : "Leader changed"}</td>
          <td>{c.abstention_recommended ? `Abstain: ${c.abstention_reasons.join(", ")}` : "Candidate survived controls"}</td></tr>)}</tbody></table>}
      {p.position_diagnostic && <section aria-label="Bounded position diagnostic">
        <h4>Site-assisted position diagnostic</h4>
        <p>{p.position_diagnostic.state === "diagnostic" && p.position_diagnostic.candidate_latitude_deg != null && p.position_diagnostic.candidate_longitude_deg != null
          ? `Candidate ${p.position_diagnostic.candidate_latitude_deg.toFixed(5)}°, ${p.position_diagnostic.candidate_longitude_deg.toFixed(5)}° · training RMS ${p.position_diagnostic.training_rms_hz?.toFixed(1)} Hz · evaluation RMS ${p.position_diagnostic.evaluation_rms_hz?.toFixed(1)} Hz.`
          : `Position diagnostic ${p.position_diagnostic.state}: ${p.position_diagnostic.reasons.join(", ")}.`}</p>
        <p>{p.position_diagnostic.fit_observation_count} fit and {p.position_diagnostic.evaluation_observation_count} evaluation observations from {p.position_diagnostic.track_count} tracks. Conditional on site-assisted identity; no position fix is claimed.</p>
      </section>}
      {p.artifacts.length > 0 && <div className="scanner-artifact-gallery" aria-label="Trajectory figures">
        {p.artifacts.map(artifact => {
          const artifactUrl = `${base}/${artifact.name}.png?sha256=${encodeURIComponent(artifact.sha256)}`;
          return <figure key={`${artifact.name}:${artifact.sha256}`}>
            <figcaption>{artifactCaption(artifact.name)}</figcaption>
            <a href={artifactUrl} target="_blank" rel="noreferrer" aria-label={`Open ${artifact.name} PNG`}>
              <div className="scanner-artifact-viewport"><img loading="lazy" src={artifactUrl} alt={`${artifact.name} for ${sessionId}`} /></div>
            </a>
          </figure>;
        })}
      </div>}
      <a href={base} download={`${sessionId}-tracking.json`}>Download tracking evidence</a>
    </>}
    <p className="scanner-artifact-caption">Tracks are reconstructed before catalogue access. TLE comparisons use deterministic randomized evaluation samples, ±500 s wrong-time controls, and a radio-polynomial control. Candidate labels do not establish satellite identity.</p>
  </section>;
}
