"""Fixed-location hard/soft association ablation over the frozen sixteen cache.

Candidates are the per-scan union of prior-production winners. This is a
prior-conditioned sensitivity analysis, never a blind catalogue result. Saved
randomized masks are used exactly; identity/timing decisions use training rows.
"""
# ruff: noqa: E402
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, time
from pathlib import Path
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import logsumexp
from types import SimpleNamespace

def _module(path):
    spec = importlib.util.spec_from_file_location("sixteen_joint_compare", path)
    mod = importlib.util.module_from_spec(spec); assert spec.loader is not None
    spec.loader.exec_module(mod); return mod
def _digest(path): return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
def _rms(parts):
    values = [x.ravel() for x in parts if len(x)]
    return float(np.sqrt(np.mean(np.concatenate(values) ** 2))) if values else None

def _track_score(track, signal_sigma=250., null_sigma=30000., signal_prior=.5):
    """Training-only hard MAP and candidate/tau-mixture evidence."""
    y, train = track.measured_hz, track.training_mask
    residual = y[None, None, :] - track.predictions_hz
    offset = np.mean(residual[:, :, train], axis=2)
    centered = residual - offset[:, :, None]
    sse = np.sum(centered[:, :, train] ** 2, axis=2)
    visible = np.broadcast_to(track.visible[:, None], sse.shape) if track.visible.ndim == 1 else track.visible
    sse = np.where(visible, sse, np.inf); n = int(train.sum())
    null = y - np.mean(y[train])
    log_null = -0.5*np.sum(null[train]**2)/null_sigma**2 - n*np.log(null_sigma) + np.log1p(-signal_prior)
    if not np.any(visible):
        return None, None, 1., 0., float(log_null), float("inf"), np.zeros_like(sse)
    hard = np.unravel_index(np.argmin(sse), sse.shape)
    log_signal = -0.5*sse/signal_sigma**2 - n*np.log(signal_sigma) + np.log(signal_prior/sse.size)
    total = logsumexp(np.r_[log_signal.ravel(), log_null]); posterior = np.exp(log_signal-total)
    soft = np.unravel_index(np.argmax(posterior), posterior.shape)
    def row(index):
        r = centered[index]
        return {"candidate_id":str(track.candidate_ids[index[0]]),"tau_s":float(track.taus_s[index[1]]),
                "training":r[train],"evaluation":r[~train]}
    positive=posterior[posterior > 0]
    return row(hard), row(soft), float(np.exp(log_null-total)), float(-np.sum(positive*np.log(positive))), float(total), float(sse[hard]), posterior

def _self_test():
    """Numerical guard for symmetry and null support without cache or truth."""
    track=SimpleNamespace(measured_hz=np.zeros(6),training_mask=np.array([1,1,1,1,0,0],bool),predictions_hz=np.zeros((2,1,6)),visible=np.array([True,True]),candidate_ids=np.array(["1","2"]),taus_s=np.array([0.]))
    hard,soft,null,entropy,_,_,posterior=_track_score(track)
    assert hard["candidate_id"] == soft["candidate_id"] == "1"
    assert np.isfinite(entropy) and entropy > 0 and np.isclose(posterior[0,0],posterior[1,0])
    hidden=SimpleNamespace(**{**track.__dict__,"visible":np.array([False,False])})
    hard,soft,null,entropy,_,_,posterior=_track_score(hidden)
    assert hard is None and soft is None and null == 1. and entropy == 0. and not np.any(posterior)

def _evaluate(cache, joint, lat, lon):
    manifest=json.loads((cache/"cache_manifest.json").read_text())
    hard_train=[]; hard_eval=[]; soft_train=[]; soft_eval=[]; nulls=[]; entropies=[]; sources={}; choices=[]; predictions=[]; soft_nll=0.; hard_sse=0.; duration_weight=0
    for scan in manifest["scans"]:
        sid=scan["session_id"]; evidence, arrays=joint.load_scan_cache(cache,sid)
        try:
            for record in evidence["tracks"]:
                prediction=joint.prediction_for_track(evidence,arrays,record,lat,lon); predictions.append(prediction)
                hard,soft,null,entropy,log_evidence,train_sse,_=_track_score(prediction)
                nulls.append(null); entropies.append(entropy)
                if hard is not None:
                    hard_train.append(hard["training"]); hard_eval.append(hard["evaluation"])
                    soft_train.append(soft["training"]); soft_eval.append(soft["evaluation"])
                    sources.setdefault(soft["candidate_id"],set()).add(sid)
                # First normalize each dense track by its training-row count, then
                # apply the production-style one-second duration weight.
                weight=len(np.unique(np.floor(prediction.times_s).astype(int))); duration_weight += weight
                soft_nll -= weight*log_evidence/int(prediction.training_mask.sum())
                if hard is not None: hard_sse += weight*train_sse/int(prediction.training_mask.sum())
                choices.append({"track_id":record["track_id"],"scan_id":sid,"hard_candidate_id":None if hard is None else hard["candidate_id"],"hard_tau_s":None if hard is None else hard["tau_s"],"soft_mode_candidate_id":None if soft is None else soft["candidate_id"],"soft_mode_tau_s":None if soft is None else soft["tau_s"],"null_posterior":null,"entropy_nats":entropy})
        finally:
            if hasattr(arrays,"close"): arrays.close()
    native=joint.score_point(0,0,predictions)
    return {"latitude_deg":lat,"longitude_deg":lon,"track_count":len(choices),"observation_count":14043,
            "native_integer_capped_weighted_rms_hz":native.residual_rmse_hz,
            "native_integer_objective_hz2":native.weighted_mse_hz2,
            "hard_training_duration_weighted_mean_sse":hard_sse/duration_weight,
            "soft_training_duration_weighted_mean_negative_log_evidence":soft_nll/duration_weight,
            "hard":{"training_rms_hz":_rms(hard_train),"evaluation_rms_hz":_rms(hard_eval)},
            "soft":{"mode_training_rms_hz":_rms(soft_train),"mode_evaluation_rms_hz":_rms(soft_eval),"mean_null_posterior":float(np.mean(nulls)),"median_null_posterior":float(np.median(nulls)),"median_entropy_nats":float(np.median(entropies))},
            "source_scan_reuse":{"distinct_sources":len(sources),"max_scans_per_source":max(map(len,sources.values()))},"track_choices":choices}

def run(args):
    if args.output.exists(): raise ValueError(f"fresh output required: {args.output}")
    manifest=json.loads((args.cache/"cache_manifest.json").read_text())
    if (manifest["tracks"],manifest["observations"]) != (553,14043): raise ValueError("not frozen corpus")
    locations=json.loads(args.locations.read_text())
    if not locations: raise ValueError("frozen joint finalists required")
    started=time.monotonic(); args.output.mkdir(parents=True); joint=_module(args.joint_tool)
    rows=[_evaluate(args.cache,joint,float(p["latitude_deg"]),float(p["longitude_deg"])) for p in locations]
    selected={"hard_training_mean_sse":min(rows,key=lambda r:r["hard_training_duration_weighted_mean_sse"]),"soft_marginal_evidence":min(rows,key=lambda r:r["soft_training_duration_weighted_mean_negative_log_evidence"])}
    orbit={"state":"insufficient","reason":"No saved production identity recurs across scans; a shared cross-scan rate has no repeated-source support and can absorb position error.","max_scans_per_source":max(r["source_scan_reuse"]["max_scans_per_source"] for r in rows),"bounded_rate_fit_run":False}
    result={"complete":True,"position_truth_used":False,"candidate_scope":"prior-conditioned per-scan union of Sacramento/Reno production winners; not full catalogue","validation":"saved randomized evaluation rows are conditional sensitivity only; historic discovery used them","mask":"exact saved production training_mask","tau_support_s":[-5,5],"tau_step_s":1.,"objective_normalization":"per-track training mean, then one-second duration weight; dense samples are not treated as independent tracks","fixed_scales":{"signal_sigma_hz":250.,"null_sigma_hz":30000.,"signal_prior":.5,"caveat":"uniform candidate/tau prior and null rates are descriptive mixture settings, not calibrated probabilities"},"cache_manifest_digest":_digest(args.cache/"cache_manifest.json"),"results_by_frozen_finalist":rows,"training_selected_methods":selected,"shared_orbit":orbit,"elapsed_s":time.monotonic()-started}
    (args.output/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fig,ax=plt.subplots(figsize=(7,4),layout="constrained"); x=np.arange(len(rows)); w=.34
    ax.bar(x-w/2,[r["hard"]["evaluation_rms_hz"] for r in rows],w,label="hard MAP"); ax.bar(x+w/2,[r["soft"]["mode_evaluation_rms_hz"] for r in rows],w,label="soft posterior mode")
    ax.set(xlabel="Frozen joint finalist",ylabel="Conditional evaluation RMS (Hz)",title="Same candidates, timing grid, and masks"); ax.set_xticks(x,[str(i+1) for i in x]); ax.grid(axis="y",alpha=.25); ax.legend(); fig.savefig(args.output/"hard_soft_rms.png",dpi=160); plt.close(fig)

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--cache",type=Path); parser.add_argument("--locations",type=Path); parser.add_argument("--output",type=Path); parser.add_argument("--joint-tool",type=Path,default=Path("tools/research/sixteen_joint_compare.py")); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test: _self_test()
    elif None in (args.cache,args.locations,args.output): parser.error("--cache, --locations, and --output are required unless --self-test")
    else: run(args)
