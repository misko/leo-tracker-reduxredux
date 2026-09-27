from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.special import roots_hermitenorm
from quality_panel_reference import log_integrand

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-panel'


def main():
    audit=json.loads((OUT/'audit.json').read_text());fig,axes=plt.subplots(1,2,figsize=(11,4))
    diagnostics=[]
    for ax,sid,label in zip(axes,dict.fromkeys(r['session_id'] for r in audit['rows']),['08:20','10:50']):
        row=next(r for r in audit['rows'] if r['session_id']==sid and r['model']=='generic')
        b=np.load(HERE/'causal-quality'/f'{sid}-bank.npz');ti=int(np.argmin(abs(b['taus']-row['tau_s'])));r=b['residuals'][row['candidate_index'],ti]
        scales=3.125*2.**np.arange(10);beta=np.linspace(r.min()-100,r.max()+100,12000);value=log_integrand(beta,r,scales,b['times'],b['pilot_flags'],'generic')[:,-1];peak=beta[np.argmax(value)]
        ax.plot(beta-peak,np.exp(value-value.max()),label='Final offset likelihood × prior')
        x,w=roots_hermitenorm(64);centers=[r[:8].mean(),np.median(r[:8])];nodes=np.concatenate([c+s/np.sqrt(8)*x[w>0] for c in centers for s in scales]);near=nodes[abs(nodes-peak)<25]
        ax.scatter(near-peak,np.zeros(len(near)),marker='|',color='red',label='64-node proposal locations')
        ax.set(xlim=(-25,25),xlabel='Offset relative to posterior peak (Hz)',ylabel='Relative density',title=f'{label}: one diagnostic hypothesis');ax.legend(fontsize=7)
        diagnostics.append(dict(session_id=sid,peak_offset_hz=float(peak),nearest_64node_distance_hz=float(abs(nodes-peak).min())))
    fig.tight_layout();fig.savefig(OUT/'offset-peaks.png',dpi=160)
    (OUT/'peak-diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')


if __name__=='__main__':main()
