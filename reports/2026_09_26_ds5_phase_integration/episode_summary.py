"""Summarize measured effects and audit the stronger reset rule's information."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from episode_trial import labels

HERE=Path(__file__).resolve().parent
OUT=HERE/'phase-episodes'

def main():
    results=json.loads((OUT/'results.json').read_text());audit=json.loads((OUT/'support-audit.json').read_text());rows=[]
    fig,ax=plt.subplots(figsize=(9,4),constrained_layout=True)
    for i,r in enumerate(x for x in results['experiments'] if x['arm']=='continuous'):
        trial=next(x for x in results['experiments'] if x['arm']=='timing_episodes' and x['session_id']==r['session_id'] and x['fold']==r['fold'])
        breaks=sorted(b['time_s'] for t in audit['tracks'] if t['session_id']==r['session_id'] for b in t['supported_breaks'])
        g=labels(np.array(r['phase_times_s']),breaks);k=np.array(r['kappa']);active=np.unique(g[k>0])
        # When every non-neutral observation is in one group, integrating the
        # other groups contributes exactly zero for every orbital hypothesis.
        equivalent=len(active)<=1
        row=dict(session_id=r['session_id'],fold=r['fold'],continuous_gain_nats=r['cfo_gain'],original_break_gain_nats=trial['cfo_gain'],supported_break_times_s=breaks,supported_active_groups=active.tolist(),supported_reset_equivalent_to_continuous=equivalent)
        if equivalent:row['supported_reset_gain_nats']=r['cfo_gain']
        rows.append(row)
        ax.bar(i-.15,r['cfo_gain'],width=.3,color='tab:blue',label='Continuous reference' if i==0 else None)
        ax.bar(i+.15,trial['cfo_gain'],width=.3,color='tab:orange',label='Original timing flags' if i==0 else None)
    ax.set_xticks(range(4),['09:50 / fold 0','09:50 / fold 1','12:00 / fold 0','12:00 / fold 1']);ax.axhline(0,color='black',lw=.8);ax.set_ylabel('Held CFO predictive gain from phase (nats)');ax.set_title('Phase-reference resets alone do not give consistent association gains');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.savefig(OUT/'association-gain.png',dpi=160);plt.close(fig)
    (OUT/'summary.json').write_text(json.dumps(dict(meaning='Supported-rule scores are an exact equivalence deduction from neutral support, not a separately rerun integrator.',comparisons=rows),indent=2)+'\n')

if __name__=='__main__':main()
