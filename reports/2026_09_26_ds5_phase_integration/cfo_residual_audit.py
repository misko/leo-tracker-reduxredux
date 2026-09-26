"""Plot residuals at a training-selected candidate and timing hypothesis."""
from pathlib import Path
import json
import numpy as np
from scipy.special import logsumexp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import catalogue_trial as T
from cfo_scale_mixture import refine_bank

HERE=Path(__file__).resolve().parent
OUT=HERE/'cfo-scale-mixture'

def main():
    model=json.loads((HERE/'timing-calibration.json').read_text())['model'];scales=[3.125,6.25,12.5,25,50,100,200,400,800,1600];rows=[]
    fig,axes=plt.subplots(4,2,figsize=(12,11),constrained_layout=True)
    for scan,sid in enumerate(['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']):
        membership=json.loads((HERE/'timing-trial'/f'{sid}-f1-q65-b161-membership.json').read_text())
        for fold in (0,1):
            prior=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());times=np.array([r['time_s'] for r in prior['observations']]);T.FOLD=fold;T.PARTITION_OVERRIDES[sid]={int(b):bool(m) for b,m in zip(T.visit_bins(sid,times),prior['phase_training_mask'])}
            for mode,(tid,membership_row) in enumerate(zip(prior['track_ids'],membership['tracks'])):
                times=np.array(membership_row['times_s']);mask=T.partition(sid,times);bank=refine_bank(dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{tid[7:19]}.npz')),model,.025)
                tr=logsumexp(np.stack([T.constant_log_evidence(bank['train_residual'],sigma) for sigma in scales]),axis=0)-np.log(len(scales));weights=tr+bank['logprior'];candidate=int(np.argmax(logsumexp(weights,axis=1)));tau=int(np.argmax(weights[candidate]));offset=bank['train_residual'][candidate,tau].mean();parts=[]
                for label,keep,key,color in [('Training',mask,'train_residual','tab:blue'),('Held',~mask,'held_residual','tab:orange')]:
                    bins=np.unique(np.floor(times[keep]).astype(int));error=bank[key][candidate,tau]-offset;assert len(bins)==len(error)
                    parts.extend([dict(time_bin_s=int(b),partition=label,residual_hz=float(e)) for b,e in zip(bins,error)])
                    axes[2*scan+mode,fold].scatter(bins+.5,error,s=20,color=color,label=label)
                ax=axes[2*scan+mode,fold];ax.axhline(0,color='black',lw=.7);ax.set_title(f"{['09:50','12:00'][scan]}, mode {mode}, fold {fold}; candidate {bank['candidate_ids'][candidate]}",fontsize=10);ax.set_xlabel('Time since scan start (s)');ax.set_ylabel('CFO residual after train offset (Hz)');ax.legend(fontsize=7);ax.grid(alpha=.2)
                row=dict(session_id=sid,fold=fold,mode=mode,candidate_id=str(bank['candidate_ids'][candidate]),training_tau_map_s=float(bank['taus'][tau]),training_offset_hz=float(offset),blocks=parts)
                rows.append(row);print(sid,fold,mode,row['candidate_id'],'tau',row['training_tau_map_s'],'largest',sorted(parts,key=lambda r:-abs(r['residual_hz']))[:3],flush=True)
    fig.savefig(OUT/'residuals.png',dpi=160);plt.close(fig)
    (OUT/'residual-audit.json').write_text(json.dumps(dict(meaning='Diagnostic at training-selected candidate and MAP timing with training-only constant offset; not the marginalized scoring model and not satellite ground truth',rows=rows),indent=2)+'\n')

if __name__=='__main__':main()
