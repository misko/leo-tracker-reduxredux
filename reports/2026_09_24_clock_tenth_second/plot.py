import json
from pathlib import Path
import matplotlib.pyplot as plt
HERE=Path(__file__).parent; d=json.loads((HERE/"results.json").read_text())
plt.figure(figsize=(7,4.5)); plt.plot(d["tau_s"],d["training_capped_loss"],marker="o",label="TRAIN"); plt.plot(d["tau_s"],d["held_capped_loss"],marker="o",label="Held diagnostic"); plt.axvline(d["selected_tau_s"],color="black",linestyle="--",label=f'selected {d["selected_tau_s"]:+.1f} s'); plt.xlabel("Shared receive-time shift (s)"); plt.ylabel("All-track capped loss"); plt.title("Fixed p0007 tenth-second clock refinement"); plt.grid(alpha=.25); plt.legend(); plt.tight_layout(); plt.savefig(HERE/"tenth_second_profile.png",dpi=180)
