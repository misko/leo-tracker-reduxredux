import json
from pathlib import Path
import matplotlib.pyplot as plt
HERE=Path(__file__).parent; d=json.loads((HERE/"results.json").read_text())
fig,axes=plt.subplots(1,2,figsize=(10,4.3))
for cell in d["results"]:
 s=[x for x in cell["scenarios"] if x["mapping"]==[0,1]]; s.sort(key=lambda x:x["full_fov_deg"]); widths=[x["full_fov_deg"] for x in s]
 axes[0].plot(widths,[x["training_capped_loss"] for x in s],marker="o",label=cell["cell_id"]); axes[1].plot(widths,[x["supported_occupied_second_fraction"] for x in s],marker="o",label=cell["cell_id"])
axes[0].set_ylabel("All-track capped training loss"); axes[1].set_ylabel("Supported occupied-second fraction")
for ax in axes: ax.set_xlabel("Full field of view (degrees)"); ax.set_xticks([10,25,30]); ax.grid(alpha=.25)
axes[0].legend(fontsize=8); fig.suptitle("Staged shared fixed-cone width sweep"); fig.tight_layout(); fig.savefig(HERE/"width_sweep.png",dpi=180)
