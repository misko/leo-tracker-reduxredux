import { useEffect, useState } from "react";

type Document = {
  schema_version: 2;
  analysis_id: "scanner-adaptive-tle-position-v2";
  session_id: string;
  input_manifest_sha256: string;
  state: "diagnostic" | "insufficient" | "failed";
  reasons: string[];
  known_position_used_for_inference: false;
  position_fix_claimed: false;
  priors: Array<{
    name: "sacramento" | "reno";
    region: { radius_km: number };
    search_complete: boolean;
    accounting: { eligible_track_count: number; eligible_observation_count: number; evaluated_point_count: number };
    selected: null | { latitude_deg: number; longitude_deg: number; capped_weighted_rmse_hz: number; spacing_km: number };
  }>;
};
type Status = {
  session_id: string;
  state: "pending" | "complete";
  manifest: null | {
    document: Document;
    artifacts: Array<{ name: "map"; sha256: string }>;
  };
};

export function AdaptiveTlePosition({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/scanner/tracking/${encodeURIComponent(sessionId)}/adaptive-tle-position-v2`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let busy = false;
    setStatus(null);
    setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch(base, { signal: controller.signal });
        if (!response.ok) throw new Error(`Adaptive position analysis unavailable (${response.status})`);
        const value = await response.json() as Status;
        const document = value.manifest?.document;
        if (value.session_id !== sessionId || (document &&
          (document.session_id !== sessionId || (inputDigest && document.input_manifest_sha256 !== inputDigest))))
          throw new Error("Adaptive position evidence does not match this capture");
        if (document && (document.known_position_used_for_inference !== false || document.position_fix_claimed !== false))
          throw new Error("Adaptive position evidence does not declare a blind diagnostic search");
        if (document && (document.schema_version !== 2 || document.analysis_id !== "scanner-adaptive-tle-position-v2" ||
          document.priors.some(prior => prior.region.radius_km !== (prior.name === "sacramento" ? 250 : 500))))
          throw new Error("Adaptive position evidence does not match the Sacramento 250 km / Reno 500 km analysis");
        if (value.manifest && (value.manifest.artifacts.length !== 1 || value.manifest.artifacts[0].name !== "map"))
          throw new Error("Adaptive position figure inventory is invalid");
        if (active) { setStatus(value); setError(null); }
      } catch (e) {
        if (active && !controller.signal.aborted) { setStatus(null); setError(String(e)); }
      } finally { busy = false; }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [base, inputDigest, sessionId]);

  const manifest = status?.manifest;
  return <section className="scanner-artifact-panel" aria-label="Adaptive all-track position search">
    <h4>Adaptive all-track position search</h4>
    <p>Sacramento uses a 250 km search radius; Reno uses 500 km. All tracks with at least 3 seconds of support and 6 observations contribute to a duration-weighted, capped RMS score. The true receiver position is used only for comparison after fitting.</p>
    <p>This bounded search reports candidate locations, not a confirmed position fix. Randomized evaluation RMS is used to select the result and is not an independent accuracy test.</p>
    {error && <p role="alert">{error}</p>}
    {!error && !manifest && <p>Adaptive position analysis is pending.</p>}
    {manifest && <>
      {manifest.document.state !== "diagnostic" && <p>{manifest.document.state}: {manifest.document.reasons.join(", ")}</p>}
      {manifest.document.priors.length > 0 && <div className="queue-table-scroll"><table className="queue-table">
        <thead><tr><th>Prior</th><th>Evidence</th><th>Best evaluated location</th><th>Selection RMS</th><th>Search</th></tr></thead>
        <tbody>{manifest.document.priors.map(prior => <tr key={prior.name}>
          <td>{prior.name === "sacramento" ? "Sacramento" : "Reno"} · {prior.region.radius_km} km</td>
          <td>{prior.accounting.eligible_track_count} tracks · {prior.accounting.eligible_observation_count} observations</td>
          <td>{prior.selected ? `${prior.selected.latitude_deg.toFixed(6)}°, ${prior.selected.longitude_deg.toFixed(6)}°` : "Unavailable"}</td>
          <td>{prior.selected ? `${prior.selected.capped_weighted_rmse_hz.toFixed(2)} Hz` : "—"}</td>
          <td>{prior.accounting.evaluated_point_count} positions · {prior.search_complete ? "completed grid" : "budget limited"}</td>
        </tr>)}</tbody>
      </table></div>}
      <div className="scanner-artifact-gallery" aria-label="Adaptive position figures">
        {manifest.artifacts.map(artifact => {
          const url = `${base}/${artifact.name}.png?sha256=${encodeURIComponent(artifact.sha256)}`;
          return <figure key={artifact.sha256}>
            <figcaption>All-track location search and reference comparison</figcaption>
            <a href={url} target="_blank" rel="noreferrer" aria-label="Open adaptive position PNG">
              <div className="scanner-artifact-viewport"><img loading="lazy" src={url} alt={`Adaptive position search for ${sessionId}`} /></div>
            </a>
          </figure>;
        })}
      </div>
      <a href={base} download={`${sessionId}-adaptive-tle-position-v2.json`}>Download adaptive position JSON</a>
    </>}
  </section>;
}
