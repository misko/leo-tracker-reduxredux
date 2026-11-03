"""Replay saved paired-gain extraction and conditional held-frame densities."""

import numpy as np
from ds23_cross_RX_gain_prediction import fit,predict
from probe_ds23_cross_RX_gain_prediction import OUT,BULK,extract,projected_gains,SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def main():
    document=read(OUT/'evaluation.json');source=read(SOURCE);records=[]
    if document['failures']:raise ValueError('all saved gain probes must finish')
    for row in document['rows']:
        original=source['rows'][row['index']];entry=row['entry'];differences=[]
        with np.load(ROOT/entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
        extracted=extract(values,entry,original['within_frame_fits']);t=extracted['time_s'];frames=np.arange(len(t))
        for mode,receivers in extracted['modes'].items():
            for fold in row['results'][mode]['folds']:
                train=frames%2==fold['parity'];test=~train
                gains=[projected_gains(r['coefficients'],r['covariance'],train) for r in receivers]
                a,b=gains[0]['gain'],gains[1]['gain'];va,vb=gains[0]['variance'],gains[1]['variance']
                for k,g in enumerate(gains):
                    saved=fold['gains'][k]
                    np.testing.assert_allclose(g['gain'],np.array(saved['gain_real'])+1j*np.array(saved['gain_imag']),rtol=0,atol=1e-8)
                    np.testing.assert_allclose(g['variance'],saved['variance'],rtol=0,atol=1e-7)
                raw={}
                for model in ['shared','independent']:
                    refit=fit(t[train],a[train],b[train],va[train],vb[train],shared=model=='shared')
                    value=predict(refit,t[test],a[test],b[test],va[test],vb[test]);raw[model]=value
                    differences.append(value-fold['actual'][model+'_held_NLL'])
                rng=np.random.default_rng(2026102130+row['index']*2+fold['parity']);surrogate=abs(b)*np.exp(1j*rng.uniform(-np.pi,np.pi,len(t)))
                null=[]
                for model in ['shared','independent']:
                    refit=fit(t[train],a[train],surrogate[train],va[train],vb[train],shared=model=='shared')
                    null.append(predict(refit,t[test],a[test],surrogate[test],va[test],vb[test]))
                differences.append(null[1]-null[0]-fold['phase_randomized_control_gains'][0])
                expected=(1+sum(v>=raw['independent']-raw['shared'] for v in fold['phase_randomized_control_gains']))/32
                if expected!=fold['phase_randomization_rank']:raise ValueError('preliminary phase-control rank changed')
        if max(abs(v) for v in differences)>1e-6:raise ValueError('gain-density or raw channel extraction changed')
        records.append(dict(index=row['index'],case=row['case'],channel=row['channel'],maximum_density_replay_difference=max(abs(v) for v in differences),
            candidate=row['results']['per_tone']['candidate_for_independent_replication'],raw_panel_sha256=sha(ROOT/entry['panel'])))
    write(OUT/'independent_replay_audit.json',dict(rows=records,raw_extraction_and_all_actual_models_replayed=True,actual_model_refits=8*len(records),
        first_surrogate_per_mode_and_fold_refitted=True,all_preliminary_surrogate_ranks_recomputed=True,
        preliminary_candidate_indices=document['candidates'],
        no_independent_probe_replication_or_full_branch_resolution_or_calibrated_CFO_precision=True,
        no_CFO_or_calibration_or_position_adopted=True,
        source_evaluation_sha256=sha(OUT/'evaluation.json')))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=sorted(document['rows'],key=lambda r:r['index']);x=np.arange(len(rows))
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),constrained_layout=True)
    for mode,color in [('flat','#b8a16a'),('per_tone','#3377aa')]:
        for parity,marker in [(0,'o'),(1,'s')]:
            axes[0].scatter(x+(parity-.5)*.15,[r['results'][mode]['folds'][parity]['actual']['held_gain'] for r in rows],
                marker=marker,color=color,s=35,label=mode.replace('_',' ')+f', fold{parity}')
    axes[0].axhline(0,color='black',lw=.8);axes[0].set(ylabel='Conditional held RX2 predictive NLL gain\npositive favors common TX phase',xlabel='Previously saved probe')
    axes[0].legend(fontsize=8)
    for parity,marker in [(0,'o'),(1,'s')]:
        axes[1].scatter(x,[r['results']['per_tone']['folds'][parity]['actual']['shared']['frequency_correction_mod750_hz'] for r in rows],marker=marker,label=f'fold{parity}')
    axes[1].set(ylabel='Conditional relative-frequency correction (Hz)\n750Hz branch not independently resolved',xlabel='Previously saved probe');axes[1].legend()
    labels=[r['case'][-4:]+f" CH{r['channel']}\nprobe{r['index']}" for r in rows]
    for ax in axes:ax.set_xticks(x,labels);ax.grid(alpha=.2)
    fig.suptitle('Noise-aware paired receiver gains: one preliminary candidate in five probes\n31 phase controls/fold; conditioned whole-probe CFO/timing; no position gain established')
    fig.savefig(OUT/'paired_receiver_gain_pilot.png',dpi=160);plt.close(fig)
    print('PAIRED_RX_GAIN_REPLAY',len(records),'raw probes; one preliminary candidate, no position update',flush=True)


if __name__=='__main__':main()
