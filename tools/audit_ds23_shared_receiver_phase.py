"""Replay shared-phase predictive densities and inspect two-signal phase closure."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

from audit_ds23_joint_receiver_iq import context
from ds23_joint_receiver_iq import JointReceiverIQ
from ds23_shared_receiver_phase import frame_statistics,phase_NLL,fit_phase_sigma
from probe_ds23_shared_receiver_phase import OUT,RAW
from run_algo01_ds23_sample import ROOT,read,write,sha


def one(row):
    samples,fs,edge,epochs,segments=context(row)
    saved=next(r for r in read(OUT/'evaluation.json')['rows'] if r['index']==row['index'])
    old_phase=next(r for r in read(RAW/'independent_replay_audit.json')['rows'] if r['index']==row['index'])
    maximum_grid_difference=0.;records=[];closure=[]
    for fold in row['folds']:
        train=np.arange(len(segments))%2==fold['parity']
        support=[ix for k,ix in enumerate(segments) if train[k]]
        common=fold['models']['common'];noise=common['noise_variance_from_training_IQ_only']
        p=np.asarray(common['fit']['parameters']);problem=JointReceiverIQ(samples,fs,edge,epochs,support,noise)
        signals=problem.signals(p);signals[1]*=problem.ratios(p)
        stats=[[frame_statistics(samples[r,ix],samples[1-r,ix],signals[r][ix],signals[1-r][ix],noise[r],noise[1-r]) for ix in segments] for r in [0,1]]
        phase=fit_phase_sigma([stats[r][k] for r in [0,1] for k in np.flatnonzero(train)])
        for r in [0,1]:
            previous=next(q for q in saved['records'] if q['parity']==fold['parity'] and q['source_receiver']==r+1)
            np.testing.assert_allclose(phase['sigma_rad'],previous['phase_model']['sigma_rad'],atol=1e-10,rtol=1e-9)
            held=[stats[r][k] for k in np.flatnonzero(~train)]
            q4096=sum(phase_NLL(s,phase['sigma_rad']) for s in held)
            q8192=sum(phase_NLL(s,phase['sigma_rad'],grid_size=8192) for s in held)
            maximum_grid_difference=max(maximum_grid_difference,abs(q4096-q8192))
            np.testing.assert_allclose(q4096,previous['held_phase_marginal_NLL'],atol=1e-6,rtol=1e-9)
            np.testing.assert_allclose(q4096,q8192,atol=1e-6,rtol=1e-9)
            records.append(dict(parity=fold['parity'],source_receiver=r+1,sigma_rad=phase['sigma_rad']))
        diagnostics=next(d for d in old_phase['frame_phase_diagnostics'] if d['parity']==fold['parity'])
        phi=np.asarray(diagnostics['phase_residual_rad']);z=np.exp(1j*(phi[:,1]-phi[:,0]))
        mean=z[train].mean();held=(z[~train]*np.exp(-1j*np.angle(mean))).mean()
        closure.append(dict(parity=fold['parity'],training_circular_coherence=float(abs(mean)),
            held_predictive_cosine=float(held.real),held_circular_coherence=float(abs(held)),
            closure_cancels_shared_receiver_phase=True,
            descriptive_only_not_an_independent_RF_randomization_test=True))
    return dict(index=row['index'],case=row['case'],window_key=row['entry']['window_key'],records=records,
        maximum4096vs8192_NLL_difference=maximum_grid_difference,phase_closure=closure,
        clock_carrier_means_and_covariance_still_from_zero_phase_noise_fit=True)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in read(RAW/'evaluation.json')['rows']])]
    rows.sort(key=lambda r:r['index'])
    fig,ax=plt.subplots(figsize=(11,4.5),layout='constrained')
    x=np.arange(len(rows))
    for offset,parity in [(-.1,0),(.1,1)]:
        ax.scatter(x+offset,[next(d['held_predictive_cosine'] for d in r['phase_closure'] if d['parity']==parity) for r in rows],label=f'Frame fold{parity}')
    ax.axhline(0,color='gray',lw=.7);ax.axhline(1,color='gray',lw=.7,ls='--')
    ax.set_xticks(x,[r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in rows],rotation=65,ha='right')
    ax.set(ylabel='Held cosine after training-only closure phase',title='Two-signal phase closure cancels a shared receiver phase')
    ax.legend(fontsize=8)
    fig.suptitle('Aggregate predictive gain does not establish two correct RF correspondences\nDescriptive closure diagnostic; no new clock or position measurement accepted',fontsize=11)
    fig.savefig(OUT/'receiver_phase_closure.png',dpi=160);plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(rows=rows,completed=len(rows),
        shared_phase_variance_refits=2*len(rows),held_normalized_density_replays=4*len(rows),
        quadrature_resolution_checks=4*len(rows),source_sha256=sha(OUT/'evaluation.json'),
        improved_predictive_density_not_proof_of_correct_correspondences_or_clock_covariance=True,
        all9_predictive_gains_not9_qualified_calibration_windows=True,
        no_position_variant_promoted=True))
    print(dict(completed=len(rows),max_grid_difference=max(r['maximum4096vs8192_NLL_difference'] for r in rows)),flush=True)


if __name__=='__main__':main()
