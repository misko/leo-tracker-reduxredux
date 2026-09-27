"""Keep exact-case accuracy separate from real-track resolution consistency."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from causal_quality_trial import SIDS

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-mixture'

def main():
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True);comparisons=[];all_stable=True
    for scan,sid in enumerate(SIDS):
        legacy=json.loads((HERE/'causal-quality'/f'{sid}-results.json').read_text());old={m['model']:m for m in legacy['models']};baseline=old['stationary']['held_log_predictive'];runs={}
        for k in (2,4,8):
            result=json.loads((OUT/f'{sid}-k{k}.json').read_text());runs[k]={m['model']:m for m in result['models']};assert len(runs[k])==2
        changes={}
        for model,color in [('generic','tab:blue'),('timing_informed','tab:orange')]:
            scores=[runs[k][model]['held_log_predictive'] for k in (2,4,8)];axes[scan,0].plot([2,4,8],np.array(scores)-baseline,'o-',color=color,label=model.replace('_',' '));axes[scan,0].axhline(old[model]['held_log_predictive']-baseline,color=color,ls=':',alpha=.6)
            a,b=[runs[k][model] for k in (4,8)];delta=b['held_log_predictive']-a['held_log_predictive'];perblock=max(abs(x['log_predictive']-y['log_predictive']) for x,y in zip(a['rows'],b['rows']) if x['held']);prob=max(np.max(abs(np.array(x['identity_probabilities'])-y['identity_probabilities'])) for x,y in zip(a['rows'],b['rows']) if x['held'])
            changes[model]=dict(held_score_change_nats=delta,max_held_block_change_nats=perblock,max_identity_probability_change=float(prob),passes_component_consistency=abs(delta)<.05 and perblock<.05)
            all_stable&=changes[model]['passes_component_consistency']
        increments=[runs[k]['timing_informed']['held_log_predictive']-runs[k]['generic']['held_log_predictive'] for k in (2,4,8)];axes[scan,1].plot([2,4,8],increments,'o-',color='tab:purple');axes[scan,1].axhline(old['timing_informed']['held_log_predictive']-old['generic']['held_log_predictive'],color='gray',ls=':',label='Legacy approximation');axes[scan,1].axhline(0,color='black',lw=.8)
        for ax in axes[scan]:ax.set_xticks([2,4,8]);ax.set_xlabel('Offset components per quality state');ax.grid(alpha=.2);ax.legend(fontsize=8)
        axes[scan,0].set_title(['08:20 UTC','10:50 UTC'][scan]+' — dotted lines: legacy approximation');axes[scan,0].set_ylabel('Held gain over exact stationary model (nats)');axes[scan,1].set_title('Additional timing-trigger gain');axes[scan,1].set_ylabel('Timing informed minus generic (nats)')
        comparisons.append(dict(session_id=sid,stationary_score=baseline,runs=[dict(components=k,scores={m:runs[k][m]['held_log_predictive'] for m in runs[k]},timing_increment=increments[j]) for j,k in enumerate((2,4,8))],four_to_eight_component_changes=changes))
    fig.suptitle('Real-track component consistency '+('passes' if all_stable else 'does not pass')+' the 0.05-nat check')
    fig.savefig(OUT/'resolution-comparison.png',dpi=160);plt.close(fig)
    (OUT/'summary.json').write_text(json.dumps(dict(component_tolerance_nats=.05,real_component_consistency_passed=bool(all_stable),meaning='Adjacent-resolution consistency is necessary evidence, not a certified error bound or timing-grid convergence proof.',scans=comparisons),indent=2)+'\n')

if __name__=='__main__':main()
