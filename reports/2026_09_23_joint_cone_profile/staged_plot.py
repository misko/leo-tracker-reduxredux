import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
HERE=Path(__file__).parent; d=json.loads((HERE/"staged_results.json").read_text()); cells=d["results"]
x=np.arange(len(cells)); base_train=[c["baseline_training_capped_loss"] for c in cells]; base_held=[c["baseline_held_capped_loss"] for c in cells]
stage_train=[c["scenarios"][0]["training_capped_loss"] for c in cells]; stage_held=[c["scenarios"][0]["held_capped_loss"] for c in cells]
support=[c["scenarios"][0]["supported_occupied_second_support"]/c["occupied_second_support"] for c in cells]
fig,axes=plt.subplots(1,2,figsize=(10,4.3)); w=.2
axes[0].bar(x-1.5*w,base_train,w,label="baseline train"); axes[0].bar(x-.5*w,base_held,w,label="baseline held"); axes[0].bar(x+.5*w,stage_train,w,label="staged train"); axes[0].bar(x+1.5*w,stage_held,w,label="staged held")
axes[0].set_ylabel("All-track capped loss"); axes[0].legend(fontsize=8); axes[0].set_ylim(0,1)
axes[1].bar(x,support,color="#4c78a8"); axes[1].set_ylabel("Compatible occupied-second fraction"); axes[1].set_ylim(0,1)
for ax in axes: ax.set_xticks(x,[c["cell_id"] for c in cells]); ax.grid(axis="y",alpha=.25)
fig.suptitle("Staged 25° full-FOV shared fixed-cone refit (mapping 0→axis 0)"); fig.tight_layout(); fig.savefig(HERE/"staged_comparison.png",dpi=180)
