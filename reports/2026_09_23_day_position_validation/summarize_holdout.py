"""Summarize the frozen full-catalogue frequency test without updating positions."""
import json
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure


def main():
    out=Path(__file__).resolve().parent
    protocol=json.loads((out/"holdout_protocol.json").read_text())
    data=json.loads((out/"heldout/results.json").read_text())
    locations=protocol["locations"]; ids=[p["location_id"] for p in locations]
    by_id={r["session_id"]:r for r in data["sessions"]}
    assert set(by_id)==set(protocol["session_ids"]) and len(data["sessions"])==16
    per_scan=[]; weights=[]; bounds=np.zeros(5,dtype=int); missing=np.zeros(5,dtype=int)
    tracks=[]
    for sid in protocol["session_ids"]:
        values=[]; previous_ids=None; weight_sum=None
        for j,lid in enumerate(ids):
            rows=[r for r in by_id[sid]["evaluation"] if r["location_id"]==lid]
            track_ids={r["track_id"] for r in rows}
            assert len(rows)==len(track_ids)
            if previous_ids is not None: assert track_ids==previous_ids
            previous_ids=track_ids
            w=np.asarray([r["weight_s"] for r in rows],float)
            rms=np.asarray([r["evaluation_rms_hz"] if r["matched"] else 800 for r in rows])
            assert np.isfinite(rms).all() and np.all(w>0)
            if weight_sum is not None: assert weight_sum==w.sum()
            weight_sum=w.sum(); values.append(float(np.sum(w*np.minimum(rms,800)**2)/w.sum()))
            missing[j]+=sum(not r["matched"] for r in rows)
            bounds[j]+=sum(r["matched"] and abs(r["tau_s"])==5 for r in rows)
        tracks.append(len(previous_ids)); per_scan.append(values); weights.append(weight_sum)
    mse=np.asarray(per_scan); w=np.asarray(weights)
    scores=np.sqrt(np.sum(mse*w[:,None],axis=0)/w.sum())
    rng=np.random.default_rng(9232416); draws=rng.integers(0,16,(10000,16))
    boot=np.sqrt(np.sum(mse[draws]*w[draws,None],axis=1)/np.sum(w[draws],axis=1)[:,None])
    difference=boot-boot[:,[0]]
    rows=[]
    for i,p in enumerate(locations):
        rows.append(dict(**p, heldout_capped_weighted_rms_hz=float(scores[i]),
            difference_from_original_best_hz=float(scores[i]-scores[0]),
            paired_scan_bootstrap_difference_hz_95pct=np.quantile(difference[:,i],[.025,.975]).tolist(),
            tau_bound_tracks=int(bounds[i]),unmatched_tracks=int(missing[i]),
            best_in_scan_resamples_pct=float(100*np.mean(np.argmin(boot,axis=1)==i))))
    result=dict(scope="Frozen five positions; all-catalogue training-only hard MAP identity/tau/CFO then randomized held-out frequencies; no position selected for deployment",
        uncertainty_scope="Whole-scan paired bootstrap frequency-score sensitivity, not a position confidence region; reconstructed track support conditioned upon",
        scans=16, tracks=int(sum(tracks)), session_ids=protocol["session_ids"],
        rows=rows,per_scan_track_count=tracks,per_scan_weight=weights,per_scan_rms_hz=np.sqrt(mse).tolist(),
        bootstrap_seed=9232416,bootstrap_draws=10000)
    (out/"heldout_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    labels=["Original 314 m", "Alternative 1.15 km", "Alternative 6.21 km", "Sacramento mean", "Reno mean"]
    fig=Figure(figsize=(12,5),layout="constrained"); ax=fig.subplots(1,2)
    for i,row in enumerate(rows):
        lo,hi=row["paired_scan_bootstrap_difference_hz_95pct"]
        ax[0].plot([lo,hi],[i,i],color="#267b9f",linewidth=3)
        ax[0].scatter(row["difference_from_original_best_hz"],i,color="#153d50",zorder=3)
    ax[0].axvline(0,color="black",linestyle="--",linewidth=1)
    ax[0].set(yticks=range(5),yticklabels=labels,xlabel="Held-out RMS difference from original location (Hz)",title="Negative favours alternative · scan-bootstrap 95% interval")
    differences=np.sqrt(mse)-np.sqrt(mse[:,[0]])
    limit=max(float(np.max(np.abs(differences))),1e-8)
    im=ax[1].imshow(differences,aspect="auto",cmap="RdBu_r",vmin=-limit,vmax=limit)
    ax[1].set(xticks=range(5),xticklabels=["original","basin 2","basin 3","Sac mean","Reno mean"],xlabel="Frozen geographic hypothesis",ylabel="Time-spanning scan index",title="Per-scan held-out score difference")
    fig.colorbar(im,ax=ax[1],label="RMS difference (Hz)")
    fig.savefig(out/"heldout_comparison.png",dpi=160)
    print(json.dumps(rows,indent=2))


if __name__=="__main__": main()
