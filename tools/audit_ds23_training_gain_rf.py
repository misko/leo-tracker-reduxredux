"""Raw-IQ/native-fit replay and scope audit of conditional RF replication."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_paired_gain_training_only import OUT,BULK,gains
from ds23_training_gain_rf import restricted_workspace
from ds23_fractional_differential_phase import fractional_geometry
from ds23_conditional_pilot_components import component_segments
from ds23_differential_frame_phase import unique_frame_intersections
from probe_ds23_cross_RX_gain_prediction import evaluate
from leo.analysis.research.retained_track_likelihood import PERIOD
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay(job):
    index=job['index'];entry=job['entry'];path=BULK/f'probe{index:03d}.json';saved=read(path)
    if saved['status']!='complete':return dict(index=index,case=entry['case'],status=saved['status'])
    with np.load(entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
    if 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest()!=entry['raw_window_sha256']:raise ValueError('native raw window changed')
    fs=entry['sample_rate_hz'];samples=[values[:,r,0].astype(float)+1j*values[:,r,1] for r in [0,1]]
    epochs=np.array(entry['epochs']);epochs[1]+=np.rint((epochs[0]-epochs[1])/(fs/750))*(fs/750)
    initial=[dict(CFO_hz=p['fractional_tracking_cfo_hz'],offset_samples=0.,modulation_ppm=0.) for p in entry['peaks']]
    geometry=[fractional_geometry(y,fs,entry['edge'],epochs[r],initial[r]) for r,y in enumerate(samples)]
    segments=[ix[16:-16] for ix in unique_frame_intersections(*geometry,component_segments(*geometry)) if len(ix)>=112]
    t=np.array([ix.mean()/fs for ix in segments]);frames=np.arange(len(t));checks=[];native_delta=[];corrected_delta=[];quality=[]
    for fold in saved['folds']:
        parity=fold['parity'];train=frames%2==parity;training=[ix for k,ix in enumerate(segments) if train[k]]
        used=np.concatenate(training);held=np.concatenate([ix for k,ix in enumerate(segments) if not train[k]])
        if np.intersect1d(used,held).size or len(used)!=fold['training_samples_per_RX'] or len(held)!=fold['held_samples_per_RX']:
            raise ValueError('native RF fitting overlaps target held IQ samples')
        fits=[restricted_workspace(y,fs,entry['edge'],epochs[r],training).fast_joint_fit(initial[r]['CFO_hz']) for r,y in enumerate(samples)]
        for r,fit in enumerate(fits):
            old=fold['native_training_fits'][r]
            for key in ['CFO_hz','offset_samples','modulation_ppm','score']:
                if abs(fit[key]-old[key])>1e-6:raise ValueError('actual native RF training refit changed')
            quality.append(not any(fit[k] for k in ['frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary']) and fit['margin']>.05)
        (a,va),(b,vb)=gains(samples,entry,epochs,fits,segments)
        np.testing.assert_allclose(a,np.asarray(fold['source_gain_real'])+1j*np.asarray(fold['source_gain_imag']),atol=1e-7,rtol=1e-10)
        np.testing.assert_allclose(b,np.asarray(fold['target_gain_real'])+1j*np.asarray(fold['target_gain_imag']),atol=1e-7,rtol=1e-10)
        oriented=[]
        for r in fold['records']:
            args=(a,b,va,vb) if r['direction']==0 else (b,a,vb,va)
            actual=evaluate(t,*args,train);old=r['actual'];difference=actual['held_gain']-old['held_gain']
            if abs(difference)>1e-5:raise ValueError('actual conditional-gain prediction refit changed')
            oriented.append(actual['shared']['frequency_correction_mod750_hz']*(1 if r['direction']==0 else -1))
            checks.append(dict(parity=parity,direction=r['direction'],held_gain_difference=difference))
        native=fits[1]['CFO_hz']-fits[0]['CFO_hz'];corrected=native+np.mean(oriented)
        native_delta.append(float((native+PERIOD/2)%PERIOD-PERIOD/2));corrected_delta.append(float((corrected+PERIOD/2)%PERIOD-PERIOD/2))
    rank=(1+sum(v>=saved['actual_score'] for v in saved['phase_control_scores']))/200
    if rank!=saved['phase_control_rank']:raise ValueError('phase-control rank changed')
    # Refit the first declared randomized control, rather than only trusting
    # stored null scores. The full199-score rank is separately recomputed.
    rng=np.random.default_rng(2026102160+index);phases=rng.uniform(-np.pi,np.pi,(199,len(t)))[0];null=[]
    for fold in saved['folds']:
        train=frames%2==fold['parity'];a=np.asarray(fold['source_gain_real'])+1j*np.asarray(fold['source_gain_imag'])
        b=np.asarray(fold['target_gain_real'])+1j*np.asarray(fold['target_gain_imag']);b=abs(b)*np.exp(1j*phases)
        va=np.asarray(fold['source_variance']);vb=np.asarray(fold['target_variance'])
        for direction in [0,1]:
            null.append(evaluate(t,*( (a,b,va,vb) if direction==0 else (b,a,vb,va)),train)['held_gain'])
    if abs(min(null)-saved['phase_control_scores'][0])>1e-5:raise ValueError('randomized raw gain control changed')
    spread=lambda v:float(abs((v[1]-v[0]+PERIOD/2)%PERIOD-PERIOD/2))
    return dict(index=index,case=entry['case'],status='complete',actual_score=saved['actual_score'],
        whole_probe_RF_score=saved['whole_probe_RF_control_score'],candidate=saved['conditional_candidate'],
        all_native_training_fits_interior_and_margin_above05=all(quality),phase_control_rank=rank,
        native_delta_RX2_minus_RX1_hz=native_delta,conditional_gain_delta_RX2_minus_RX1_hz=corrected_delta,
        native_fold_difference_hz=spread(native_delta),conditional_fold_difference_hz=spread(corrected_delta),
        actual_gain_refits=checks,actual_native_RF_refits=4,first_randomized_control_refit=True,
        all_199_null_scores_rank_recomputed=True,raw_source_sha256=sha(path))


def main():
    protocol=read(OUT/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('frozen training-only RF source changed')
    with ProcessPoolExecutor(max_workers=10) as pool:rows=[f.result() for f in as_completed([pool.submit(replay,j) for j in protocol['jobs']])]
    rows.sort(key=lambda r:r['index']);accepted=[r for r in rows if r.get('candidate')]
    result=dict(rows=rows,completed=sum(r['status']=='complete' for r in rows),conditional_candidates=len(accepted),
        candidate_native_RF_quality_pass=sum(r['all_native_training_fits_interior_and_margin_above05'] for r in accepted),
        actual_native_RF_refits=sum(r.get('actual_native_RF_refits',0) for r in rows),
        actual_gain_model_refits=sum(len(r.get('actual_gain_refits',[])) for r in rows),
        all_raw_extractions_and_actual_RF_optimizations_replayed=True,
        first_control_refitted_per_probe_not_all199_controls=True,
        per_frame_extraction_variances_conditioned_including_held_frame_noise_statistics=True,
        native_coarse_GLRT_seed_and_epoch_selection_remain_conditioned=True,
        uncertainty_and750Hz_branch_and_covariance_with_primary_GLRT_NOT_validated=True,
        no_absolute_frequency_measurement_or_position_algorithm_promoted=True,protocol_sha256=sha(OUT/'protocol.json'))
    write(OUT/'independent_replay_audit.json',result)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    ax=axes[0]
    for r in rows:
        if r['status']!='complete':continue
        ax.scatter(r['whole_probe_RF_score'],r['actual_score'],color='tab:blue' if r['candidate'] else '.6')
        ax.annotate(r['case'].split('-')[-1],(r['whole_probe_RF_score'],r['actual_score']),xytext=(3,3),textcoords='offset points',fontsize=6)
    ax.axhline(0,color='black',lw=.7);ax.axvline(0,color='black',lw=.7)
    ax.set(xscale='symlog',yscale='symlog',xlabel='Whole-probe RF-conditioned held gain',ylabel='Training-only RF held gain',
        title=f'{len(accepted)}/{len(rows)} conditional candidates after native RF refits');ax.grid(alpha=.2)
    ax=axes[1]
    for k,r in enumerate(accepted):
        ax.plot([r['native_fold_difference_hz'],r['conditional_fold_difference_hz']],[k,k],color='.7',lw=1)
    ax.scatter([r['native_fold_difference_hz'] for r in accepted],range(len(accepted)),label='Native RF fits',color='tab:orange',s=24)
    ax.scatter([r['conditional_fold_difference_hz'] for r in accepted],range(len(accepted)),label='Native + paired-gain correction',color='tab:blue',s=24)
    ax.set_yticks(range(len(accepted)),[r['case'].split('-')[-1] for r in accepted],fontsize=8)
    ax.set(xlabel='Difference between frame-fold RX2−RX1 estimates (Hz)',title='Repeatability only; uncertainty NOT calibrated')
    ax.grid(axis='x',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('19 new scans · same-frame-support native RF training ablation\nNo TLE/GPS, no new recording, no satellite identity or positioning accuracy claim')
    fig.savefig(OUT/'training_only_RF_controls.png',dpi=175);plt.close(fig)
    print({k:v for k,v in result.items() if k!='rows'},flush=True)


if __name__=='__main__':main()
