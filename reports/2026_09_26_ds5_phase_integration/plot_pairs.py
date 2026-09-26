"""Show every two-mode dwell without selecting visually favorable examples."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def main():
    plan=json.loads((HERE/'plan.json').read_text());fig,axes=plt.subplots(2,3,figsize=(14,8),constrained_layout=True)
    for column,scan in enumerate(plan['scans']):
        rows=json.loads((HERE/(scan['session_id']+'.json')).read_text())['rows']
        for visit in scan['selected']:
            if len(visit['modes'])!=2:continue
            series=[sorted([r for r in rows if r['visit']==visit['visit'] and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
            a,b=[np.array([r['coefficients']['full']['phase_rad'] for r in s]) for s in series]
            dd=np.angle(np.exp(1j*(b-a)))
            axes[0,column].plot([r['start_ms']+3.5 for r in series[0]],np.degrees(dd),'o-',ms=3,label=str(visit['visit']))
        axes[0,column].set(title=scan['metadata']['capture_start_utc'][11:16]+' UTC',xlabel='Dwell time (ms)',ylabel='Mode1 − mode0 phase (deg)')
        axes[0,column].legend(title='Visit',fontsize=7,ncol=2)
        controls=json.loads((HERE/'shifted-controls.json').read_text())
        rs=[r for r in controls['rows'] if r['session_id']==scan['session_id']]
        axes[1,column].scatter([r['exact_R'] for r in rs],[r['shifted_R'] for r in rs],s=20)
        axes[1,column].plot([0,1],[0,1],'--',c='gray');axes[1,column].set(xlabel='Simultaneous RX held coherence R',ylabel='3 ms shifted RX1 held coherence R',xlim=(0,1),ylim=(0,1))
        for ax in axes[:,column]:ax.grid(alpha=.2)
    fig.suptitle('All selected two-mode dwells and independent receiver-time controls')
    fig.savefig(HERE/'pair-differences-controls.png',dpi=170);plt.close(fig)

if __name__=='__main__':main()
