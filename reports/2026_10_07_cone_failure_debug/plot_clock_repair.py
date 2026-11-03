"""Scientific diagnostic: same retained paired data before/after clock restart."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from leo.analysis.regional_position_score import PositionObjective,circular
from leo.contracts.regional_position import PositionScore
from dataclasses import replace

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("clock_plot_helpers",HERE/"annealing/experiment.py")
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
doc,old,obs,prior,bank,cp,prefix=helpers.loader.load("2139")
anneal=json.loads((HERE/"annealing/2139.json").read_text())
before=next(r for r in anneal["selections"] if r["option"]=="anneal" and r["arm"]=="zero-c")
anchors=json.loads((HERE/"paired_background/anchor_results.json").read_text())
case=next(c for c in anchors["cases"] if c["case"]=="2139")
after=next(r for r in case["selections"] if r["model"]=="independent" and r["arm"]=="zero-c")
assert before["basin"]==after["basin"]
basin=before["basin"]
assoc=cp.get(prefix+":"+basin+":association")["result"]
cal=cp.get(prefix+":"+basin+":calibration")["result"]
obj=PositionObjective(obs,bank.select(assoc["selected_indices"]),prior,
    replace(PositionScore(**doc["configuration"]["scores"]["V16"]),relative_sigma_s=1.),
    receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]))
pairs=json.loads((HERE/"identity/paired_topone.json").read_text())["cases"]["2139"]["100ns"]["rows"]
i=np.array([p["row0"] for p in pairs]);j=np.array([p["row1"] for p in pairs])
t=(obs.times_s[i]+obs.times_s[j])/2
fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharex=True)
for ax,r,label in zip(axes,[before,after],["Before: frequency-width continuation","After: RX0-anchored clock initialization"]):
    v=np.asarray(r["vector"]);clock=obj.baseline+obj.design@v[2:7]
    residual=circular(obs.measured_hz[j]-obs.measured_hz[i]-clock[j]+clock[i])
    for channel in np.unique(obs.channel[i]):
        mask=obs.channel[i]==channel
        ax.scatter(t[mask],residual[mask],s=15,alpha=.75,label=f"Channel {channel}")
    ax.axhline(0,color="black",lw=.8);ax.grid(alpha=.2);ax.set_xlim(0,300)
    ax.set_xlabel("Receive time in scan (seconds)");ax.set_ylabel("Observed − modeled RX frequency difference (Hz)")
    ax.set_title(f"{label}\nMedian absolute error: {np.median(abs(residual)):,.1f} Hz\nPosition error: {r['horizontal_error_m']/1000:.2f} km",fontsize=11)
axes[1].legend(fontsize=8,ncol=2)
fig.suptitle("14:39 PDT: correcting a false receiver-clock mode without changing the likelihood",fontsize=13)
fig.text(.5,.015,"Same 236 retained pairs; ≤100 ns inferred pilot epoch; c = 0; timing σ = 1 s. Different vertical scales. Identity is not decoded; location remains inaccurate.",ha="center",fontsize=8)
fig.tight_layout(rect=(0,.05,1,.91))
fig.savefig(HERE/"clock_repair.png",dpi=180);fig.savefig(HERE/"clock_repair.svg");plt.close(fig)
