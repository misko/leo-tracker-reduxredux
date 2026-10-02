"""Close view of selected paths; full candidate-lattice plot is preserved separately."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from screen_seed_prefix import sealed
HERE=Path(__file__).resolve().parent


def main():
    data=sealed(HERE/'candidate-path-v1.json')
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True)
    for ax,row in zip(axes,data['tracks']):
        original=row['results']['original'];poly=np.polyfit(original['times_s'],original['frequencies_hz'],2)
        for name in ('original','primary','margin_only'):
            p=row['results'][name];t=np.array(p['times_s']);y=np.array(p['frequencies_hz'])
            ax.plot(t,y-np.polyval(poly,t),'.-',label=name)
        ax.set_title(f"RX{row['receiver_id']}");ax.set_ylabel('Hz minus original quadratic');ax.grid(alpha=.2);ax.legend()
    axes[-1].set_xlabel('Seconds from first original candidate')
    fig.suptitle('Selected path detail: RX1 distortion persists despite candidate changes')
    fig.tight_layout();fig.savefig(HERE/'candidate-path-detail-v1.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
