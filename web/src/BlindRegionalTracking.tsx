import { useEffect, useState } from "react";

type Document = {
  session_id: string; input_manifest_sha256: string;
  state: "diagnostic" | "insufficient" | "failed"; reasons: string[];
  known_position_used_for_association: false; known_position_used_for_inference: false;
  site_conditioned_candidates: false;
  region: { center_latitude_deg: number; center_longitude_deg: number; width_km: number; height_km: number };
  accounting: { track_count: number; associated_track_count: number; eligible_observation_count: number; excluded_count: number };
  tracks: Array<{ track_id: string; state: string; catalogue_size: number; unassigned_weight: number;
    candidates: Array<{ catalog_number: number; soft_weight: number }>; reasons: string[] }>;
  position_modes: Array<{ rank: number; state: string; latitude_deg: number | null; longitude_deg: number | null;
    training_score: number | null; heldout_score: number | null; reasons: string[] }>;
  evaluation: { modes: Array<{ rank: number; horizontal_error_m: number }> } | null;
};
type Status = { session_id: string; state: "pending" | "complete"; manifest: null | {
  document: Document; artifacts: Array<{ name: string; sha256: string }>;
} };
const labels: Record<string, string> = {
  "blind-association": "Blind satellite associations",
  "blind-position": "Denver-region position search",
  "blind-position-modes": "Alternative blind position estimates",
};

export function BlindRegionalTracking({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/scanner/tracking/${encodeURIComponent(sessionId)}/blind-regional`;
  useEffect(() => {
    const controller = new AbortController(); let active = true; let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const response = await fetch(base, { signal: controller.signal });
        if (!response.ok) throw new Error(`Blind tracking unavailable (${response.status})`);
        const value = await response.json() as Status;
        const document = value.manifest?.document;
        if (value.session_id !== sessionId || (document &&
          (document.session_id !== sessionId || (inputDigest && document.input_manifest_sha256 !== inputDigest))))
          throw new Error("Blind tracking evidence does not match this capture");
        if (document && (document.known_position_used_for_association !== false ||
          document.known_position_used_for_inference !== false || document.site_conditioned_candidates !== false))
          throw new Error("Blind tracking evidence does not declare independent association");
        if (active) { setStatus(value); setError(null); }
      } catch (e) { if (active && !controller.signal.aborted) setError(String(e)); }
      finally { busy = false; }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [base, inputDigest, sessionId]);
  const manifest = status?.manifest;
  const d = manifest?.document;
  return <section className="scanner-artifact-panel" aria-label="Denver-region blind tracking and positioning">
    <h3>Denver-region blind tracking and positioning</h3>
    <p>Satellite association and receiver position are inferred together within the declared Denver-centred region. Sausalito coordinates and its satellite shortlist are excluded from this fit. The geographic range remains an explicit prior.</p>
    {error && <p role="alert">{error}</p>}
    {!error && !d && <p>Blind association and positioning are pending. Sausalito-assisted results are reported separately.</p>}
    {d && !error && <>
      <p>State: {d.state} · centre {d.region.center_latitude_deg.toFixed(4)}°, {d.region.center_longitude_deg.toFixed(4)}° · east/west ±{(d.region.width_km / 2).toFixed(0)} km · north/south ±{(d.region.height_km / 2).toFixed(0)} km.</p>
      <p>{d.accounting.track_count} tracks evaluated · {d.accounting.associated_track_count} associated diagnostically · {d.accounting.eligible_observation_count} eligible observations · {d.accounting.excluded_count} recorded exclusions.</p>
      {d.reasons.map((reason, i) => <p key={i}>{reason}</p>)}
      {d.position_modes.length > 0 && <table className="scanner-table" aria-label="Blind position estimates">
        <thead><tr><th>Mode</th><th>Estimated latitude, longitude</th><th>Error after fitting</th><th>Held-out score</th></tr></thead>
        <tbody>{d.position_modes.map(mode => {
          const evaluation = d.evaluation?.modes.find(item => item.rank === mode.rank);
          return <tr key={mode.rank}><td>{mode.rank}{mode.rank === 1 ? " · training leader" : ""}</td>
            <td>{mode.latitude_deg == null || mode.longitude_deg == null ? mode.state : `${mode.latitude_deg.toFixed(6)}°, ${mode.longitude_deg.toFixed(6)}°`}</td>
            <td>{evaluation == null ? "Unavailable" : `${(evaluation.horizontal_error_m / 1000).toFixed(3)} km`}</td>
            <td>{mode.heldout_score?.toFixed(2) ?? "Unavailable"}</td></tr>;
        })}</tbody>
      </table>}
      <p>Scores and association weights are composite evidence, not calibrated probabilities. These coordinates are diagnostic estimates, not GPS measurements or a validated position fix. Reference error is evaluated only after fitting.</p>
      {d.tracks.length > 0 && <details><summary>Blind satellite candidates for {d.tracks.length} tracks</summary>
        <table className="scanner-table" aria-label="Blind satellite candidates"><thead><tr><th>Track</th><th>State</th><th>Candidate weights</th><th>Unassigned</th><th>Catalogue size</th></tr></thead>
          <tbody>{d.tracks.map(track => <tr key={track.track_id}><td>{track.track_id}</td><td>{track.state}</td>
            <td>{track.candidates.map(c => `NORAD ${c.catalog_number}: ${(100 * c.soft_weight).toFixed(1)}%`).join(" · ") || "None"}</td>
            <td>{(100 * track.unassigned_weight).toFixed(1)}%</td><td>{track.catalogue_size}</td></tr>)}</tbody>
        </table>
      </details>}
      <div className="scanner-artifact-gallery" aria-label="Blind tracking figures">
        {manifest?.artifacts.map(artifact => {
          const url = `${base}/${artifact.name}.png?sha256=${encodeURIComponent(artifact.sha256)}`;
          return <figure key={artifact.name}><figcaption>{labels[artifact.name] ?? artifact.name}</figcaption>
            <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${labels[artifact.name] ?? artifact.name} PNG`}>
              <div className="scanner-artifact-viewport"><img loading="lazy" src={url} alt={`${labels[artifact.name] ?? artifact.name} for ${sessionId}`} /></div>
            </a></figure>;
        })}
      </div>
      <a href={base} download={`${sessionId}-blind-regional.json`}>Download blind tracking and positioning JSON</a>
    </>}
  </section>;
}
