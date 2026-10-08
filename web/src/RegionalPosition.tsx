import { useEffect, useState } from "react";

type Estimate = {
  latitude_deg: number; longitude_deg: number; horizontal_error_m: number;
  posterior_rms_hz: number | null; coefficient_hz_per_ghz: number;
  converged: boolean; boundary: boolean;
};
type Method = {
  name: "T1AT" | "V16"; state: "diagnostic" | "insufficient";
  points: unknown[]; search_stop_reason: string; deferred_cells: number;
  arms: Array<{ name: "fitted-c" | "zero-c"; selected: Estimate | null; reasons: string[] }>;
};
type Status = {
  session_id: string; state: "pending" | "complete";
  manifest: null | {
    document: {
      schema_version: 1 | 2; analysis_id: "scanner-regional-position-v1" | "scanner-regional-position-v2";
      configuration?: { protocol?: string; run?: { slope_half_width_hz_s?: number } };
      session_id: string; input_manifest_sha256: string;
      prior_latitude_deg: number; prior_longitude_deg: number; prior_radius_km: number;
      known_position_used_for_inference: false; position_fix_claimed: false;
      refinement: "off"; windows: number; methods: Method[];
      rf_ablation_scope: "final-score-shared-fitted-c-calibration-and-association";
    };
    artifacts: Array<{ name: "T1AT" | "V16"; sha256: string }>;
  };
};

function verify(value: Status, sessionId: string, inputDigest?: string, version = 1) {
  const doc = value.manifest?.document;
  if (value.session_id !== sessionId || (doc && (doc.session_id !== sessionId ||
    (inputDigest && doc.input_manifest_sha256 !== inputDigest))))
    throw new Error("Regional position evidence does not match this capture");
  if (!["pending", "complete"].includes(value.state) ||
    (value.state === "complete") !== Boolean(value.manifest))
    throw new Error("Regional position publication is incomplete");
  if (!doc || !value.manifest) return;
  if (doc.schema_version !== version || doc.analysis_id !== `scanner-regional-position-v${version}` ||
    doc.prior_latitude_deg !== 38.5816 || doc.prior_longitude_deg !== -121.4944 || doc.prior_radius_km !== 250 ||
    doc.known_position_used_for_inference !== false || doc.position_fix_claimed !== false ||
    doc.refinement !== "off" || doc.rf_ablation_scope !== "final-score-shared-fitted-c-calibration-and-association")
    throw new Error("Regional position evidence does not match the Sacramento comparison");
  const methods = version === 2 ? "V16" : "T1AT,V16";
  if (version === 2 && (doc.configuration?.protocol !== "sacramento-hard60-v1" ||
    doc.configuration?.run?.slope_half_width_hz_s !== 60 ||
    doc.methods.some(method => method.arms.some(arm => arm.selected && !arm.selected.converged))))
    throw new Error("Hard60 policy or convergence evidence is invalid");
  if (doc.methods.map(method => method.name).join(",") !== methods ||
    doc.methods.some(method => method.arms.map(arm => arm.name).join(",") !== "fitted-c,zero-c") ||
    value.manifest.artifacts.map(artifact => artifact.name).join(",") !== methods ||
    value.manifest.artifacts.some(artifact => !/^sha256:[0-9a-f]{64}$/.test(artifact.sha256)))
    throw new Error("Regional position method or figure inventory is invalid");
}

export function RegionalPosition({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prefix = `/api/v1/scanner/tracking/${encodeURIComponent(sessionId)}/regional-position-v`;
  const version = status?.manifest?.document.schema_version ?? 2;
  const base = `${prefix}${version}`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch(`${prefix}2`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Regional position analysis unavailable (${response.status})`);
        let value = await response.json() as Status;
        verify(value, sessionId, inputDigest, 2);
        if (!value.manifest) {
          const historical = await fetch(`${prefix}1`, { signal: controller.signal });
          if (historical.ok) {
            const old = await historical.json() as Status;
            verify(old, sessionId, inputDigest, 1);
            if (old.manifest) value = old;
          }
        }
        if (active) { setStatus(value); setError(null); }
      } catch (e) {
        if (active && !controller.signal.aborted) { setStatus(null); setError(String(e)); }
      } finally { busy = false; }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [prefix, sessionId, inputDigest]);
  const manifest = status?.manifest;
  return <section className="scanner-artifact-panel" aria-label="Hard60 Sacramento positioning">
    <h4>Hard60 Sacramento positioning</h4>
    <p>Hard60 searches the Sacramento 250 km prior with V16, a 2 s relative timing prior, ±60 Hz/s bounds on added receiver slopes, and a 40 → 20 → 10 → 5 km grid. The receiver reference measures error after selection.</p>
    <p>Fitted RF calibration and c = 0 share upstream calibration and association. Frequency RMS and position error measure different things. Results are bounded diagnostics, not confirmed position fixes.</p>
    {manifest && version === 1 && <p>Historical T1AT/V16 comparison. This capture has no published Hard60 result yet.</p>}
    {error && <p role="alert">{error}</p>}
    {!error && !manifest && <p>Hard60 analysis is pending.</p>}
    {manifest && <>
      <p>{manifest.document.windows} original windows · extra IQ/GLRT refinement off.</p>
      {manifest.document.methods.map(method => {
        const artifact = manifest.artifacts.find(item => item.name === method.name)!;
        const url = `${base}/${method.name}.png?sha256=${encodeURIComponent(artifact.sha256)}`;
        return <section key={method.name} aria-label={`${method.name} position result`}>
          <h5>{method.name === "T1AT" ? "T1AT / C0" : version === 2 ? "Hard60 / V16" : "V16"}</h5>
          <p>{method.points.length} evaluated positions · {method.search_stop_reason} · {method.deferred_cells} deferred cells.</p>
          <div className="queue-table-scroll"><table className="queue-table">
            <thead><tr><th>RF arm</th><th>Selected location</th><th>Reference error</th><th>Frequency RMS</th><th>Fit status</th></tr></thead>
            <tbody>{method.arms.map(arm => <tr key={arm.name}>
              <td>{arm.name === "zero-c" ? "c = 0" : "Fitted c"}</td>
              <td>{arm.selected ? `${arm.selected.latitude_deg.toFixed(6)}°, ${arm.selected.longitude_deg.toFixed(6)}°` : `Unavailable: ${arm.reasons.join(", ")}`}</td>
              <td>{arm.selected ? `${(arm.selected.horizontal_error_m / 1000).toFixed(2)} km` : "—"}</td>
              <td>{arm.selected?.posterior_rms_hz == null ? "—" : `${arm.selected.posterior_rms_hz.toFixed(1)} Hz`}</td>
              <td>{arm.selected ? `${arm.selected.converged ? "Stationary" : "Not converged"}${arm.selected.boundary ? "; boundary reached" : ""}` : "Insufficient evidence"}</td>
            </tr>)}</tbody>
          </table></div>
          <div className="scanner-artifact-gallery"><figure>
            <figcaption>{method.name} search, RF comparison and reference error</figcaption>
            <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${method.name} position PNG`}>
              <div className="scanner-artifact-viewport"><img loading="lazy" width={1080} height={960} style={{ width: "100%", objectFit: "contain" }} src={url} alt={`${method.name} Sacramento position search for ${sessionId}`} /></div>
            </a>
          </figure></div>
        </section>;
      })}
      <a href={base} download={`${sessionId}-regional-position-v${version}.json`}>Download position JSON</a>
    </>}
  </section>;
}
