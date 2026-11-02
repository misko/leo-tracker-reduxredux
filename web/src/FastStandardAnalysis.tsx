import { useEffect, useState } from "react";

type Arm = { endpoint_latlon: number[]; associated_points: number; associated_percent: number;
  tracks: number; satellites: number; residual_rms_hz: number; evaluation_error_m?: number | null };
type Analysis = { schema_version: number; state: string; model_version: string; selected_model: string;
  decision: string; glrt_points: number; arms: Record<"c0" | "fitted_c", Arm>;
  evaluation_reference?: { latitude_deg: number; longitude_deg: number } | null;
  artifacts: {name: string; sha256: string}[] };
const labels: Record<string,string> = {"ch1-4-all":"CH1–4 · GLRT, satellite owners and fitted orbital curves",
  "ch5-8-all":"CH5–8 · GLRT, satellite owners and fitted orbital curves",
  "ch1-4-unassociated":"CH1–4 · Unassociated GLRT and polynomial tracks",
  "ch5-8-unassociated":"CH5–8 · Unassociated GLRT and polynomial tracks",
  "ch1-4-residuals":"CH1–4 · Satellite residuals", "ch5-8-residuals":"CH5–8 · Satellite residuals",
  "track-rms":"RMS for every associated track", position:"Published positions · both calibration arms"};

export function FastStandardAnalysis({runId}:{runId:string}) {
  const [data,setData]=useState<Analysis|null>(null);const [error,setError]=useState("");
  const base=`/api/v2/fast-scans/${encodeURIComponent(runId)}/standard-analysis`;
  useEffect(()=>{
    const controller=new AbortController();let busy=false;setData(null);setError("");
    const refresh=async()=>{if(busy)return;busy=true;try{
      const response=await fetch(base,{signal:controller.signal});
      if(!response.ok)throw new Error(`Standard analysis unavailable (${response.status})`);
      const value=await response.json() as Analysis;
      if(value.schema_version!==1 || value.model_version!=="algo07-causal-guarded-reassociation-v1")throw new Error("Standard analysis belongs to another algorithm");
      if(!controller.signal.aborted){setData(value);setError("");}
    }catch(e){if(!controller.signal.aborted)setError(String(e));}finally{busy=false;}};
    void refresh();const timer=setInterval(()=>void refresh(),10000);
    return()=>{controller.abort();clearInterval(timer);};
  },[base]);
  const complete=data?.state==="complete";
  return <section className="scanner-results-panel" aria-label="Standard ALGO07 analysis">
    <h3>Standard analysis · ALGO07</h3>
    <p role="status">{complete ? `Complete · ${data.selected_model===data.model_version ? "guarded reassociation accepted" : `retained ${data.selected_model.split("-")[0].toUpperCase()} solution`}` : "Awaiting ALGO07 localization and its verified figures"}</p>
    {error && <p role="alert">{error}</p>}
    {complete && <>
      <table className="scanner-table"><thead><tr><th>Calibration</th><th>Published position</th><th>Evaluation error</th><th>GLRT associated</th><th>Tracks / satellites</th><th>Residual RMS</th></tr></thead>
        <tbody>{(["fitted_c","c0"] as const).map(arm=>{const a=data.arms[arm];return <tr key={arm}>
          <td>{arm==="fitted_c"?"Fitted c · default":"c = 0 · control"}</td>
          <td>{a.endpoint_latlon.map(n=>n.toFixed(6)).join(", ")}</td>
          <td>{a.evaluation_error_m==null?"Reference unavailable":`${a.evaluation_error_m.toFixed(1)} m`}</td>
          <td>{a.associated_points.toLocaleString()} / {data.glrt_points.toLocaleString()} · {a.associated_percent.toFixed(2)}%</td>
          <td>{a.tracks} / {a.satellites}</td><td>{a.residual_rms_hz.toFixed(2)} Hz</td>
        </tr>;})}</tbody></table>
      {data.evaluation_reference && <p>Evaluation reference: {data.evaluation_reference.latitude_deg.toFixed(8)}, {data.evaluation_reference.longitude_deg.toFixed(8)}. Used only to report error after fitting.</p>}
      <p>Every figure below uses this ALGO07 result and its published GLRT ownership. Red points are unassociated. Residuals are conditional model diagnostics.</p>
      <p>The association percentage uses the qualified native GLRT points supplied to ALGO07.</p>
      {data.artifacts.map(a=>{const url=`${base}/${encodeURIComponent(a.name)}.png?sha256=${encodeURIComponent(a.sha256)}`;return <figure key={`${a.name}:${a.sha256}`}>
        <figcaption><a href={url} target="_blank" rel="noreferrer">{labels[a.name]??a.name} · PNG</a></figcaption>
        <img src={url} alt={labels[a.name]??a.name} loading="lazy" style={{width:"100%"}} />
      </figure>;})}
      <a href={base} download={`${runId}-algo07.json`}>Download standard ALGO07 result</a>
    </>}
  </section>;
}
