from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent/'joint-phase'

def main():
    summary=[];fig,axes=plt.subplots(2,3,figsize=(14,7),constrained_layout=True)
    for row,sid in enumerate(['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']):
        d=json.loads((HERE/(sid+'.json')).read_text());scored=json.loads((HERE/(sid+'-scores.json')).read_text());shared=json.loads((HERE/(sid+'-baseline-scores.json')).read_text());rows=d['rows'];origin=min(r['utc_ns'] for r in rows);err=[];supported=[]
        for r in rows:
            a,b=r['modes'];error=np.angle(np.exp(1j*((b['evaluation']['phase_rad']-a['evaluation']['phase_rad'])-(b['train']['phase_rad']-a['train']['phase_rad']))));err.append(error);supported.append(r['both_qualified'])
        err=np.array(err);supported=np.array(supported)
        for selected,color,label in [(False,'gray','Unqualified retained'),(True,'tab:green','Both modes qualified')]:
            rr=[r for r in rows if r['both_qualified']==selected]
            axes[row,0].scatter([(r['utc_ns']-origin)/1e9 for r in rr],np.degrees([np.angle(np.exp(1j*(r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad']))) for r in rr]),s=14,color=color,label=label)
        axes[row,0].set_xlabel('Time since first window (s)');axes[row,0].set_ylabel('Joint double-difference phase (deg)');axes[row,0].legend(fontsize=7)
        all_scores=scored['experiments']+[dict(e,arm='shared_baseline') for e in shared['experiments']]
        for offset,arm,color in [(-.25,'original_all','gray'),(0,'joint_qualified','tab:blue'),(.25,'shared_baseline','tab:orange')]:
            values=[next(e['cfo_gain'] for e in all_scores if e['arm']==arm and e['sigma']==sigma and e['fold']==fold) for sigma,fold in [(100,0),(100,1),(200,0),(200,1)]]
            axes[row,1].bar(np.arange(4)+offset,values,width=.24,color=color,label=arm.replace('_',' '))
        axes[row,1].axhline(0,color='black',lw=.7);axes[row,1].set_xticks(range(4),['100/f0','100/f1','200/f0','200/f1']);axes[row,1].set_xlabel('CFO σ (Hz) / whole-dwell fold');axes[row,1].set_ylabel('Held CFO gain over CFO-only (nats)');axes[row,1].legend(fontsize=7)
        for p in shared['donor_priors']:axes[row,2].plot(p['baseline_m'],p['probabilities'],label=f"CFO σ={p['sigma']} Hz")
        axes[row,2].set_xlabel('Signed baseline length (m)');axes[row,2].set_ylabel('Transferred discrete prior mass');axes[row,2].legend(fontsize=7)
        for ax,title in zip(axes[row],['Joint phase with separate qualification','Association comparison','Baseline inferred from other scan']):ax.set_title(['09:50 UTC','12:00 UTC'][row]+'\n'+title,fontsize=11);ax.grid(alpha=.15)
        summary.append(dict(session_id=sid,windows=len(rows),both_qualified_windows=int(supported.sum()),qualified_dwells=len({r['visit'] for r in rows if r['both_qualified']}),all_DD_rms_deg=float(np.degrees(np.sqrt(np.mean(err**2)))),qualified_DD_rms_deg=float(np.degrees(np.sqrt(np.mean(err[supported]**2)))),elapsed_s=d['elapsed_s'],scores=[{k:e[k] for k in ('fold','sigma','arm','cfo_gain','phase_gain_vs_constant','top_before','top_after','maximum_probability_change')} for e in all_scores],donor_priors=shared['donor_priors']))
    fig.savefig(HERE/'results.png',dpi=160);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=summary),indent=2)+'\n')
    comparisons=[]
    for path in sorted(HERE.glob('*-baseline-q65-b161-scores.json')):
        fine=json.loads(path.read_text());coarse=json.loads(path.with_name(path.name.replace('-q65-b161','')).read_text())
        for a,b in zip(coarse['experiments'],fine['experiments']):
            assert (a['fold'],a['sigma'])==(b['fold'],b['sigma'])
            comparisons.append(dict(target=fine['protocol']['target_scan'],fold=a['fold'],sigma=a['sigma'],cfo_gain_change=b['cfo_gain']-a['cfo_gain'],phase_score_change=b['phase_held_vs_uniform']-a['phase_held_vs_uniform']))
    if comparisons:
        (HERE/'convergence.json').write_text(json.dumps(dict(comparisons=comparisons,max_abs_cfo_gain_change=max(abs(r['cfo_gain_change']) for r in comparisons)),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in s.items() if k not in ('scores','donor_priors')} for s in summary],indent=2))

if __name__=='__main__':main()
