"""Audit candidate-update gains separately from generic phase predictability."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from phase_factor import phase_evidence

HERE=Path(__file__).resolve().parent

def main():
    rows=[]
    for path in sorted(HERE.glob('catalogue-alias-trial-balanced-f*.json')):
        if path.name.endswith('-protocol.json'):continue
        d=json.loads(path.read_text());protocol=d['protocol']
        for g in d['groups']:
            if g['status']!='scored':continue
            y=np.array([r['dd_phase'] for r in g['observations']]);train=np.array(g['phase_training_mask'])
            for e in g['experiments']:
                k=e['kappa'];constant=float(phase_evidence(y,np.zeros(len(y)),np.full(len(y),k))-phase_evidence(y[train],np.zeros(train.sum()),np.full(train.sum(),k)))
                old=np.asarray(g['cfo_only_probabilities']);new=np.asarray(e['posterior_probabilities'])
                rows.append(dict(source=path.name,fold=protocol['fold'],dispersion='dispersion' in path.name,kappa=k,phase_train_dwells=int(train.sum()),phase_held_dwells=int((~train).sum()),held_cfo_blocks=g['left_candidates'][0]['held_blocks']+g['right_candidates'][0]['held_blocks'],cfo_held_gain=e['cfo_held_gain'],phase_held_gain_vs_constant=e['phase_held_log_predictive_vs_uniform']-constant,max_posterior_probability_change=float(np.max(abs(new-old))),top_pair_changed=bool(np.argmax(old)!=np.argmax(new))))
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),constrained_layout=True)
    for fold,color in [(0,'#1768ac'),(1,'#d1495b')]:
        rr=[r for r in rows if r['dispersion'] and r['fold']==fold]
        axes[0].plot([r['kappa'] for r in rr],[r['cfo_held_gain'] for r in rr],'o-',color=color,label=f'Fold {fold}')
        axes[1].plot([r['kappa'] for r in rr],[r['phase_held_gain_vs_constant'] for r in rr],'o-',color=color,label=f'Fold {fold}')
    axes[0].set(ylabel='Held CFO predictive gain (nats)',title='Small candidate-weight changes')
    axes[1].set(ylabel='Held orbital-phase gain over constant DD (nats)',title='Is geometry better than a constant difference?')
    for ax in axes:
        ax.axhline(0,c='gray',ls='--');ax.set_xlabel('Phase concentration κ (sensitivity)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Real catalogue trial: one nine-dwell pair · training-only CFO dispersion')
    fig.savefig(HERE/'catalogue-trial.png',dpi=170);plt.close(fig)
    (HERE/'catalogue-summary.json').write_text(json.dumps(dict(rows=rows,interpretation='Retrospective two-fold comparison on one track pair; candidate-weight proxy, not identity truth. Constant-DD comparison separates generic phase consistency from geometry.'),indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
