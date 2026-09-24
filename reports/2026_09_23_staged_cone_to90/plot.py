import json
from pathlib import Path
import matplotlib.pyplot as plt
HERE=Path(__file__).parent; d=json.loads((HERE/"results.json").read_text())
fig,axes=plt.subplots(1,2,figsize=(11,4.5))
for cell in d["results"]:
 rows=sorted([x for x in cell["scenarios"] if x["mapping"]==[0,1]],key=lambda x:x["full_fov_deg"]); x=[r["full_fov_deg"] for r in rows]
 axes[0].plot(x,[100*r["supported_occupied_second_fraction"] for r in rows],marker="o",label=cell["cell_id"])
 axes[1].plot(x,[r["held_capped_loss"] for r in rows],marker="o",label=cell["cell_id"])
axes[0].set_ylabel("Supported occupied-second coverage (%)"); axes[1].set_ylabel("All-track held capped loss")
for ax in axes: ax.set_xlabel("Full field of view (degrees)"); ax.set_xticks(d["full_fov_deg"]); ax.grid(alpha=.25)
axes[0].legend(fontsize=8); fig.suptitle("Staged shared fixed-cone sweep through 90° full FOV"); fig.tight_layout(); fig.savefig(HERE/"coverage_to90.png",dpi=180)
