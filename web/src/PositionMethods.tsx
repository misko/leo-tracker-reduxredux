import { useEffect, useState } from "react";

type MethodName = "expanded-doppler" | "orbit-corrected" | "identity-mixture";
type MethodResult = {
  method: MethodName;
  state: "insufficient" | "diagnostic" | "failed";
  latitude_deg: number | null;
  longitude_deg: number | null;
  horizontal_error_m: number | null;
  reasons: string[];
};
type Manifest = {
  document: {
    session_id: string;
    input_manifest_sha256: string;
    reference_position: { source: "user-provided-report-reference"; latitude_deg: number; longitude_deg: number } | null;
    methods: MethodResult[];
  };
  artifacts: Array<{ method: MethodName; sha256: string }>;
};
type Status = { session_id: string; state: "pending" | "complete"; manifest: Manifest | null };

const labels: Record<MethodName, string> = {
  "expanded-doppler": "Expanded Doppler",
  "orbit-corrected": "Orbit corrected",
  "identity-mixture": "Identity mixture",
};

export function PositionMethods({ sessionId, inputDigest }: { sessionId: string; inputDigest?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/scanner/tracking/${encodeURIComponent(sessionId)}/position-methods`;

  useEffect(() => {
    const controller = new AbortController(); let active = true; let busy = false;
    setStatus(null); setError(null);
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const response = await fetch(base, { signal: controller.signal });
        if (!response.ok) throw new Error(`Position methods unavailable (${response.status})`);
        const value = await response.json() as Status;
        const document = value.manifest?.document;
        if (value.session_id !== sessionId || (document &&
          (document.session_id !== sessionId || (inputDigest && document.input_manifest_sha256 !== inputDigest))))
          throw new Error("Position method evidence does not match this capture");
        if (active) { setStatus(value); setError(null); }
      } catch (e) { if (active && !controller.signal.aborted) setError(String(e)); }
      finally { busy = false; }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [base, inputDigest, sessionId]);

  const manifest = status?.manifest;
  return <section aria-label="Conditional position methods">
    <h4>Conditional position methods</h4>
    <p>These estimates are conditional on catalogue identity and model assumptions. They are not GPS measurements or independent position fixes.</p>
    {error && <p role="alert">{error}</p>}
    {!error && !manifest && <p>Position method evidence is pending.</p>}
    {manifest && <>
      <div className="scanner-artifact-gallery" aria-label="Position method figures">
        {manifest.artifacts.map(artifact => {
          const result = manifest.document.methods.find(item => item.method === artifact.method);
          const url = `${base}/${artifact.method}.png?sha256=${encodeURIComponent(artifact.sha256)}`;
          return <figure key={artifact.method}>
            <figcaption>{labels[artifact.method]}</figcaption>
            <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${labels[artifact.method]} PNG`}>
              <div className="scanner-artifact-viewport"><img loading="lazy" src={url} alt={`${labels[artifact.method]} diagnostic for ${sessionId}`} /></div>
            </a>
            {result?.state === "diagnostic" && result.latitude_deg != null && result.longitude_deg != null
              ? <p>{result.latitude_deg.toFixed(6)}°, {result.longitude_deg.toFixed(6)}°{result.horizontal_error_m == null ? "" : ` · ${(result.horizontal_error_m / 1000).toFixed(3)} km from the user-supplied reference`}</p>
              : <p>{result?.state ?? "pending"}{result?.reasons.length ? `: ${result.reasons.join(", ")}` : ""}</p>}
          </figure>;
        })}
      </div>
      {manifest.document.reference_position
        ? <p>The user-supplied report reference is used only to evaluate error after fitting.</p>
        : <p>No user-supplied reference was provided, so no position error is reported.</p>}
      <a href={base} download={`${sessionId}-position-methods.json`}>Download position methods JSON</a>
    </>}
  </section>;
}
