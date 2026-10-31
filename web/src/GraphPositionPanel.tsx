import { useEffect, useState } from "react";

type Position = { latitude_deg: number; longitude_deg: number };
type Estimate = { model_version: string; position: Position | null };
type GraphPosition = { state: string; selected_model: string | null; decision?: string;
  baseline?: Estimate | null; incumbent?: Estimate | null; selected?: Estimate | null;
  fallback?: boolean; reason?: string | null };

function coordinates(position: Position | null | undefined) {
  return position ? `${position.latitude_deg.toFixed(6)}°, ${position.longitude_deg.toFixed(6)}°` : "Awaiting qualified position";
}

function modelLabel(model: string | null | undefined) {
  switch (model) {
    case "algo04-causal-numerical-v1": return "ALGO04";
    case "algo03-causal-predictive-v1": return "ALGO03";
    case "algo02-causal-family-v1": return "ALGO02";
    default: return model ?? "Pending";
  }
}

export function GraphPositionPanel({ runId }: { runId: string }) {
  const [view, setView] = useState<GraphPosition | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setView(null); setError("");
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch(`/api/v2/fast-scans/${encodeURIComponent(runId)}/graph-position`, { signal: controller.signal });
        if (response.status === 404) return;
        if (!response.ok) throw new Error(`Graph localization request failed (${response.status})`);
        const value = await response.json() as GraphPosition;
        if (!controller.signal.aborted) { setView(value); setError(""); }
      } catch (failure) {
        if (!controller.signal.aborted) setError(String(failure));
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [runId]);
  if (!view || view.state === "disabled") return error ? <p role="alert">{error}</p> : null;
  return <section className="scanner-results-panel" aria-label="Graph localization">
    <h3>Graph localization · {modelLabel(view.selected_model)}</h3>
    <p>{view.fallback ? (view.decision?.endsWith("_fallback")
      ? view.decision.replace(/_fallback$/, " fallback")
      : `${modelLabel(view.selected?.model_version)} fallback`)
      : view.decision === "ALGO04_additive" ? "ALGO04 numerical add-on" : view.decision ?? "Awaiting localization"}
      {view.reason && ` · ${view.reason}`}</p>
    <dl className="adaptive-summary">
      <div><dt>Published fitted-c position</dt><dd>{coordinates(view.selected?.position)}</dd></div>
      <div><dt>Published model</dt><dd>{view.selected?.model_version ?? "Pending"}</dd></div>
      {view.incumbent && <div><dt>Published ALGO03 incumbent fitted-c position</dt><dd>{coordinates(view.incumbent.position)}</dd></div>}
      <div><dt>Original ALGO02 fitted-c position</dt><dd>{coordinates(view.baseline?.position)}</dd></div>
    </dl>
    {error && <p role="alert">{error}</p>}
  </section>;
}
