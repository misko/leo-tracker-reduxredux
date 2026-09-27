"""Display all tested boundaries, including negative and ineligible controls."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from boundary_controls import OUT,SESSIONS

def main():
    data=json.loads((OUT/'results.json').read_text());assert len(data['results'])==8
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True);rows=[]
    for r in data['results']:
        scan=SESSIONS.index(r['session_id']);ax=axes[scan,r['mode']];color=['tab:blue','tab:orange'][r['fold']]
        controls=[v for v in r['trials'] if v['eligible'] and v['kind']=='control'];pilots=[v for v in r['trials'] if v['eligible'] and v['kind']=='pilot_break']
        ax.scatter([v['cut_s'] for v in controls],[v['gain_nats'] for v in controls],color=color,s=35,label=f"Ordinary boundaries, fold {r['fold']}")
        for v in pilots:ax.scatter(v['cut_s'],v['gain_nats'],marker='*',s=180,color=color,edgecolor='black',label=f"Pilot timing, fold {r['fold']}")
        rows.append(dict(scan=['09:50','12:00'][scan],mode=r['mode'],fold=r['fold'],eligible_controls=len(controls),rejected_controls=sum(not v['eligible'] for v in r['trials']),control_gain_range=[min(v['gain_nats'] for v in controls),max(v['gain_nats'] for v in controls)],pilot_boundary_gain=pilots[0]['gain_nats'] if pilots else None,generic_model_gain=r['generic_model_mixture_gain_nats'],pilot_model_gain=r['pilot_model_mixture_gain_nats'],pilot_minus_generic=r['pilot_model_mixture_gain_nats']-r['generic_model_mixture_gain_nats']))
        ax.set_title(f"{['09:50','12:00'][scan]} UTC, mode {r['mode']}");ax.set_xlabel('Boundary time since scan start (s)');ax.set_ylabel('Held CFO gain over stationary scale (nats)')
    for ax in axes.flat:ax.axhline(0,color='black',lw=.8);ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.savefig(OUT/'boundary-gains.png',dpi=160);plt.close(fig)
    (OUT/'summary.json').write_text(json.dumps(dict(meaning='All eligible controls shown. Correlated folds on four development tracks, not independent population evidence.',comparisons=rows),indent=2)+'\n')

if __name__=='__main__':main()
