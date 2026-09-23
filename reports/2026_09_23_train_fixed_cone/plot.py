import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).parent
d=json.loads((HERE/"results.json").read_text()); rows=d["rows"]
fig,axes=plt.subplots(1,2,figsize=(11,4.5),sharey=True)
for ax,field,title in zip(axes,["held_inside_duration_s","held_sampled_whole_inside_duration_s"],["Midpoint proxy","Start/midpoint/end sampled diagnostic"]):
    for ci in range(1,6):
        actual=[]; controls=[]
        for width in d["widths_deg"]:
            a=[r for r in rows if r["cell_id"]==f"cell_{ci}" and r["mapping"]==[0,1] and r["width_deg"]==width and r["kind"]=="actual"]
            actual.append(sum(r[field] for r in a)/sum(r["held_duration_s"] for r in a))
            per=[]
            for p in range(20):
                q=[r for r in rows if r["cell_id"]==f"cell_{ci}" and r["mapping"]==[0,1] and r["width_deg"]==width and r["permutation"]==p]
                per.append(sum(r[field] for r in q)/sum(r["held_duration_s"] for r in q))
            controls.append(np.mean(per))
        line=ax.plot(d["widths_deg"],actual,marker="o",label=f"cell {ci}")[0]
        ax.plot(d["widths_deg"],controls,linestyle="--",alpha=.65,color=line.get_color())
    ax.set_title(title); ax.set_xlabel("Fixed cone half-width (degrees)"); ax.grid(alpha=.25); ax.set_xticks(d["widths_deg"])
axes[0].set_ylabel("Pooled held duration coverage")
axes[0].legend(ncol=2,fontsize=8)
fig.suptitle("Actual receiver labels (solid) vs 20-control mean (dashed)\nOne common training-selected orientation across 12 scans")
fig.tight_layout(); fig.savefig(HERE/"held_fixed_cone_controls.png",dpi=180)
