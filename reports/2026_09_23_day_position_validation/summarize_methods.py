"""Report every frozen method on all seven complete replication blocks."""
import csv
import json
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure


def main():
    out=Path(__file__).resolve().parent
    base=json.loads((out/"replication/results.json").read_text())
    ablation=json.loads((out/"ablations/results.json").read_text())
    hard=json.loads((out/"ablations/hard_training_supplemental.json").read_text())
    rows=[]
    for group in ablation["groups"]:
        for row in group["results"]:
            rows.append(dict(group_id=group["group_id"],scan_count=group["scan_count"],
                method=row["method"],latitude_deg=row["latitude_deg"],longitude_deg=row["longitude_deg"],error_km=row["error_km"]))
    for group in hard["groups"]:
        row=group["result"]
        rows.append(dict(group_id=group["group_id"],scan_count=group["scan_count"],method=row["method"],
            latitude_deg=row["latitude_deg"],longitude_deg=row["longitude_deg"],error_km=row["error_km"]))
    for group in base["results"]:
        for row in group["controls"]:
            rows.append(dict(group_id=group["group_id"],scan_count=group["scan_count"],method=row["method"],
                latitude_deg=row["latitude_deg"],longitude_deg=row["longitude_deg"],error_km=row["error_km"]))
    summaries=[]
    for method in sorted({r["method"] for r in rows}):
        values=[r["error_km"] for r in rows if r["method"]==method and r["scan_count"]==16]
        assert len(values)==7, (method,len(values))
        summaries.append(dict(method=method,groups=7,min_error_km=min(values),median_error_km=float(np.median(values)),
            max_error_km=max(values),within_1km=sum(x<=1 for x in values),within_0_5km=sum(x<=.5 for x in values)))
    (out/"method_summary.json").write_text(json.dumps(dict(scope="Conditional method replication; seven complete16-scan blocks; partial4 excluded from aggregate",summary=summaries,rows=rows),indent=2)+"\n")
    with (out/"method_errors.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
    text=["| Method | Median error km | Range km | Within 1 km |", "|---|---:|---:|---:|"]
    text += [f"| {r['method']} | {r['median_error_km']:.3f} | {r['min_error_km']:.3f}–{r['max_error_km']:.3f} | {r['within_1km']}/7 |" for r in summaries]
    (out/"METHODS_TABLE.md").write_text("\n".join(text)+"\n")
    chosen=[("native_integer_capped","Joint integer"),
        ("soft_marginal_train","Soft association"),
        ("hard_training_mean_sse","Hard training MSE"),
        ("timing-0.25s-duration-capped-rmse-800hz-identity-evaluation","Quarter-second timing"),
        ("timing-0.25s-uncertainty-floor-pseudo-huber-identity-training","Robust quarter-second"),
        ("mean-sacramento","Mean Sacramento"),("mean-reno","Mean Reno")]
    fig=Figure(figsize=(12,5.5),layout="constrained");ax=fig.subplots(1,2)
    for i,(method,label) in enumerate(chosen):
        values=[r["error_km"] for r in rows if r["method"]==method and r["scan_count"]==16]
        ax[0].scatter(np.arange(1,8),values,label=label,s=24,alpha=.8)
        ax[1].plot([min(values),max(values)],[i,i],color="#bbbbbb",linewidth=2)
        ax[1].scatter(values,[i]*7,s=25,alpha=.7)
        ax[1].scatter(float(np.median(values)),i,marker="D",s=55,color="black",zorder=4)
    ax[0].axhline(.314,color="black",linestyle="--",linewidth=1,label="Original 314 m")
    ax[0].set(yscale="log",xlabel="Disjoint sixteen-scan block",ylabel="Actual error (km)",title="New data: every complete block")
    ax[0].legend(fontsize=7,ncol=2);ax[0].grid(alpha=.2)
    ax[1].axvline(.314,color="black",linestyle="--",linewidth=1)
    ax[1].set(xscale="log",yticks=range(len(chosen)),yticklabels=[x[1] for x in chosen],xlabel="Actual error (km; diamond = median)",title="Distributions, not best-case results")
    ax[1].grid(axis="x",alpha=.2);fig.savefig(out/"method_comparison.png",dpi=170)
    print("\n".join(text))


if __name__=="__main__": main()
