"""Report sequential held scores without equating confidence with identity truth."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from causal_quality_trial import OUT,SIDS

def main():
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True);summary=[]
    accuracy=json.loads((OUT/'accuracy-audit.json').read_text())
    if not accuracy['overall_accuracy_gate_passed']:fig.suptitle('Approximate filter: accuracy gate failed; predictive gains remain provisional',fontsize=13)
    for scan,sid in enumerate(SIDS):
        data=json.loads((OUT/f'{sid}-results.json').read_text());models={m['model']:m for m in data['models']};assert len(models)==3
        baseline=models['stationary'];t=np.array([r['time_s'] for r in baseline['rows']]);keep=np.array([r['held'] for r in baseline['rows']]);base=np.array([r['log_predictive'] for r in baseline['rows']]);ids=data['catalogue_candidate_ids'];scores={}
        for kind,color in [('stationary','gray'),('generic','tab:blue'),('timing_informed','tab:orange')]:
            m=models[kind];scores[kind]=m['held_log_predictive']
            vals=np.array([r['log_predictive'] for r in m['rows']]);prob=np.array([r['identity_probabilities'] for r in m['rows']]);entropy=-np.sum(prob*np.log2(np.maximum(prob,1e-300)),axis=1)
            if kind!='stationary':axes[scan,0].plot(t[keep],np.cumsum((vals-base)[keep]),color=color,label=kind.replace('_',' '))
            axes[scan,1].plot(t[keep],entropy[keep],color=color,label=kind.replace('_',' '))
        flags=data['plan']['pilot_flags']
        for i,flag in enumerate(flags):
            if flag and i+1<len(t):axes[scan,0].axvline(t[i+1],color='gray',ls=':',alpha=.6)
        for ax in axes[scan]:ax.set_xlabel('Time since scan start (s)');ax.grid(alpha=.2);ax.legend(fontsize=8)
        axes[scan,0].axhline(0,color='black',lw=.7);axes[scan,0].set_ylabel('Cumulative held gain over stationary (nats)');axes[scan,0].set_title(['08:20 UTC','10:50 UTC'][scan]+' — dotted lines: first prediction after flag')
        axes[scan,1].set_ylabel('Catalogue identity entropy (bits)');axes[scan,1].set_title('Conditional uncertainty, not identity accuracy')
        summary.append(dict(session_id=sid,blocks=len(t),warmup_blocks=int((~keep).sum()),held_blocks=int(keep.sum()),timing_flags=sum(flags),candidates=len(ids),held_scores=scores,generic_gain=scores['generic']-scores['stationary'],timing_gain=scores['timing_informed']-scores['stationary'],timing_increment=scores['timing_informed']-scores['generic'],final_top_candidates={kind:ids[m['rows'][-1]['top_candidate_index']] for kind,m in models.items()}))
    fig.savefig(OUT/'sequential-comparison.png',dpi=160);plt.close(fig)
    (OUT/'summary.json').write_text(json.dumps(dict(meaning='First-eight-block proposals, then sequential prediction conditional on retrospectively selected track membership. No independent satellite truth.',accuracy_gate_passed=accuracy['overall_accuracy_gate_passed'],scans=summary),indent=2)+'\n')

if __name__=='__main__':main()
