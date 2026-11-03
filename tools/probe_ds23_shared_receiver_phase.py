"""Predictive covariance control for shared receiver phase, without refitting held IQ."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

from audit_ds23_joint_receiver_iq import context
from ds23_joint_receiver_iq import JointReceiverIQ
from ds23_shared_receiver_phase import frame_statistics,phase_NLL,fit_phase_sigma
from probe_ds23_joint_receiver_iq import OUT as RAW
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_shared_receiver_phase'
INDEPENDENT=ROOT/'reports/2026_10_21_ds23_joint_iq_independent_control/evaluation.json'


def one(row):
    samples,fs,edge,epochs,segments=context(row)
    baseline=next(r for r in read(INDEPENDENT)['rows'] if r['index']==row['index'])
    records=[]
    for fold in row['folds']:
        train=np.arange(len(segments))%2==fold['parity']
        support=[ix for k,ix in enumerate(segments) if train[k]]
        saved=fold['models']['common'];noise=saved['noise_variance_from_training_IQ_only']
        problem=JointReceiverIQ(samples,fs,edge,epochs,support,noise)
        p=np.asarray(saved['fit']['parameters']);signals=problem.signals(p);signals[1]*=problem.ratios(p)
        stats=[]
        for source in [0,1]:
            stats.append([frame_statistics(samples[source,ix],samples[1-source,ix],signals[source][ix],
                signals[1-source][ix],noise[source],noise[1-source]) for ix in segments])
        training=[stats[source][k] for source in [0,1] for k in np.flatnonzero(train)]
        phase=fit_phase_sigma(training)
        for source in [0,1]:
            held=[stats[source][k] for k in np.flatnonzero(~train)]
            score=sum(phase_NLL(s,phase['sigma_rad']) for s in held)
            zero=sum(phase_NLL(s,0.) for s in held)
            np.testing.assert_allclose(zero,saved['predictions'][source]['NLL'],atol=1e-6,rtol=1e-9)
            other=next(r for r in baseline['records'] if r['parity']==fold['parity'] and r['source_receiver']==source+1)
            records.append(dict(parity=fold['parity'],source_receiver=source+1,phase_model=phase,
                held_phase_marginal_NLL=score,held_zero_phase_NLL=zero,
                phase_vs_zero_held_gain=zero-score,
                phase_vs_independent_target_held_gain=other['independent_target_raw_NLL']-score))
    return dict(index=row['index'],case=row['case'],window_key=row['entry']['window_key'],cohort=row['cohort'],records=records,
        all_directions_folds_beat_independent=all(r['phase_vs_independent_target_held_gain']>0 for r in records),
        one_training_only_receiver_phase_variance_per_fold_shared_by_both_signals=True,
        mean_clock_carrier_epoch_rate_and_ratios_not_refit_after_phase_marginalization=True,
        no_new_clock_or_position_measurement_qualified=True)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    OUT.mkdir(exist_ok=True)
    protocol=dict(raw_source_sha256=sha(RAW/'evaluation.json'),independent_control_sha256=sha(INDEPENDENT),workers=6,
        source_tools={n:sha(ROOT/'tools'/n) for n in [__file__.split('/')[-1],'ds23_shared_receiver_phase.py']},
        model='one wrapped Gaussian relative RX phase per frame; same phase multiplies all components; variance learned on training frames only',
        objective='normalized raw-IQ target prediction; source-gain covariance retained; no held target coefficient or phase fit',
        one_variance_from_sum_of_both_RX_training_conditional_NLLs=True,
        RF_mean_parameters_fixed_from_preexisting_training_joint_IQ_fit=True,
        quadrature_grid=4096,no_GPS_TLE_satellite_ID_new_RF_or_position_used=True)
    p=OUT/'protocol.json'
    if p.exists() and read(p)!=protocol:raise ValueError('frozen shared receiver phase control changed')
    if not p.exists():write(p,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in read(RAW/'evaluation.json')['rows']])]
    rows.sort(key=lambda r:r['index'])
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    x=np.arange(len(rows));labels=[r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in rows]
    for offset,parity in [(-.1,0),(.1,1)]:
        axes[0].scatter(x+offset,[next(q['phase_model']['sigma_rad'] for q in r['records'] if q['parity']==parity) for r in rows],label=f'Frame fold{parity}')
    axes[0].set(title='Training-only common receiver phase SD',ylabel='Phase SD(rad)');axes[0].legend(fontsize=8)
    for key,label,color in [('phase_vs_zero_held_gain','vs zero phase noise','tab:blue'),('phase_vs_independent_target_held_gain','vs independent target','tab:orange')]:
        axes[1].scatter(x,[min(q[key] for q in r['records']) for r in rows],label=label,color=color)
    axes[1].axhline(0,color='gray',lw=.7);axes[1].set_yscale('symlog',linthresh=1)
    axes[1].set(title='Worst held gain across both RX/folds',ylabel='Positive favors shared phase model');axes[1].legend(fontsize=8)
    for ax in axes:ax.set_xticks(x,labels,rotation=65,ha='right')
    fig.suptitle('One shared receiver phase distribution; no per-track phase freedom\nPredictive covariance control only: mean carrier/clock and localization remain unchanged',fontsize=11)
    fig.savefig(OUT/'shared_phase_predictive_control.png',dpi=160);plt.close(fig)
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(p),
        candidates_for_joint_phase_noise_refit=[r['index'] for r in rows if r['all_directions_folds_beat_independent']],
        no_position_method_or_absolute_CFO_covariance_promoted=True))
    print([(r['index'],r['all_directions_folds_beat_independent'],min(q['phase_vs_independent_target_held_gain'] for q in r['records'])) for r in rows],flush=True)


if __name__=='__main__':main()
