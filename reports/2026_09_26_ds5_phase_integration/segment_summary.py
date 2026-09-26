"""Plot the controlled uncertainty comparison separately from carrier phase gains."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from segment_catalogue_trial import OUT

def main():
    uncertainty=json.loads((OUT/'uncertainty-ablation.json').read_text())['results']
    phase=json.loads((OUT/'phase-results.json').read_text())['experiments']+json.loads((OUT/'phase-scale-only-results.json').read_text())['experiments']
    fig,axes=plt.subplots(1,2,figsize=(13,4.6),constrained_layout=True)
    ua=['separate_offsets_shared_scale','shared_offset_separate_scales','separate_offsets_separate_scales'];pa=['continuous_identity_and_offset','same_identity_offset_reset','independent_episode_identities','same_identity_shared_offset_separate_scales']
    summary=[]
    for fold in (0,1):
        base=next(r['mode0_held_log_predictive'] for r in uncertainty if r['fold']==fold and r['arm']=='shared_offset_shared_scale')
        gains=[next(r['mode0_held_log_predictive'] for r in uncertainty if r['fold']==fold and r['arm']==a)-base for a in ua]
        pg=[next(r['cfo_gain'] for r in phase if r['fold']==fold and r['arm']==a) for a in pa]
        axes[0].bar(np.arange(3)+(fold-.5)*.34,gains,width=.34,label=f'Fold {fold}')
        axes[1].bar(np.arange(4)+(fold-.5)*.34,pg,width=.34,label=f'Fold {fold}')
        summary.append(dict(fold=fold,uncertainty_gains=dict(zip(ua,gains)),phase_gains=dict(zip(pa,pg))))
    axes[0].set_xticks(range(3),['Offset reset\nonly','Separate uncertainty\nonly','Both']);axes[0].set_title('CFO model changes: gain over shared offset and scale')
    axes[1].set_xticks(range(4),['Original','Both reset','Separate\nidentities','Separate\nuncertainty']);axes[1].set_title('Additional gain from carrier phase within each model')
    for ax in axes:ax.axhline(0,color='black',lw=.8);ax.set_ylabel('Held CFO predictive gain (nats)');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.savefig(OUT/'model-comparison.png',dpi=160);plt.close(fig)
    (OUT/'comparison.json').write_text(json.dumps(dict(meaning='Exploratory retrospective comparisons on identical observed blocks. Positive CFO uncertainty gains do not establish identity accuracy or carrier-phase benefit.',results=summary),indent=2)+'\n')

if __name__=='__main__':main()
