import { useEffect, useState } from "react";

type Product = {
  session_id: string; input_manifest_sha256: string; sample_rate_hz: number;
  trajectory_state: string; tle_state: string; reasons: string[];
  physical_group_count: number; eligible_group_count: number; attempted_group_count: number;
  deferred_group_count: number;
  catalogue_exclusions: Array<{ catalog_number: number; name: string; reason: string }>;
  unscored_groups: Array<{ physical_group_id: string; reason: string }>;
  tle_candidates: Array<{ physical_group_id: string; leading_catalog_number: number | null;
    support_span_s: number; abstention_recommended: boolean; abstention_reasons: string[] }>;
  artifacts: Array<{ name: "trajectory" | "trajectory-tle"; sha256: string }>;
};
type Status = { session_id: string; state: string; phase: string; failure_summary: string | null; product: Product | null };

export function ScannerTrackingPanel({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("trajectory-tle");
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
  const artifact = p?.artifacts.find(a => a.name === selected) ?? p?.artifacts[0];
  return <section className="scanner-artifact-panel" aria-label="Shared satellite trajectory tracking">
    <header><div><span>TRAJECTORY AND CATALOGUE EVIDENCE</span><h3>Cross-channel Doppler trajectories</h3></div>
      <small>{p ? `${p.sample_rate_hz / 1e6} MS/s · trajectories: ${p.trajectory_state} · TLE: ${p.tle_state}` : status?.phase ?? "Loading tracking status…"}</small></header>
    {error && <p role="alert">{error}</p>}
    {status?.failure_summary && <p role="alert">{status.failure_summary}</p>}
    {!p && !error && <p>Tracking will run automatically after scan analysis completes.</p>}
    {p && <>
      <p>{p.eligible_group_count} eligible of {p.physical_group_count} groups across hypotheses · {p.attempted_group_count} comparisons attempted · {p.deferred_group_count} deferred.</p>
      {p.tle_state === "pending" && <p>Measured trajectories are available; catalogue comparisons are still processing.</p>}
      {p.tle_state === "no-eligible-groups" && <p>No group has the required 20 observations spanning at least 20 seconds.</p>}
      {p.reasons.map((reason, i) => <p key={i}>{reason}</p>)}
      {p.unscored_groups.map(g => <p key={g.physical_group_id}>Unscored group: {g.reason}</p>)}
      {p.catalogue_exclusions.length > 0 && <details><summary>{p.catalogue_exclusions.length} catalogue-labelled debris objects excluded before matching</summary>
        <ul>{p.catalogue_exclusions.map(c => <li key={c.catalog_number}>NORAD {c.catalog_number} · {c.name}</li>)}</ul></details>}
      {p.tle_candidates.length > 0 && <table className="scanner-table" aria-label="Shared TLE diagnostics"><thead><tr><th>Candidate</th><th>Support</th><th>Disposition</th></tr></thead>
        <tbody>{p.tle_candidates.map(c => <tr key={c.physical_group_id}><td>{c.leading_catalog_number === null ? "Restricted null" : `NORAD ${c.leading_catalog_number}`}</td>
          <td>{c.support_span_s.toFixed(1)} s</td><td>{c.abstention_recommended ? `Abstain: ${c.abstention_reasons.join(", ")}` : "Candidate survived controls"}</td></tr>)}</tbody></table>}
      {artifact && <><div role="tablist" aria-label="Trajectory figures">{p.artifacts.map(a => <button key={a.name} role="tab" aria-selected={a.name === artifact.name} onClick={() => setSelected(a.name)}>
        {a.name === "trajectory" ? "Measured trajectories" : "TLE comparison"}</button>)}</div>
        <div className="scanner-artifact-viewport"><img loading="lazy" src={`${base}/${artifact.name}.png`} alt={`${artifact.name} for ${sessionId}`} /></div></>}
      <a href={base} download={`${sessionId}-tracking.json`}>Download tracking evidence</a>
    </>}
    <p className="scanner-artifact-caption">Tracks are reconstructed before catalogue access. TLE comparisons use chronological heldout data, ±500 s wrong-time controls, and a radio-polynomial control. Candidate labels do not establish satellite identity.</p>
  </section>;
}
