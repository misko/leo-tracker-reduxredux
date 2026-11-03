"""Conditional RF phase prediction on five previously saved paired RX probes.

This changes channel extraction and the prediction test, not the RF observations
or the old whole-probe CFO/timing estimates. The750Hz frequency ambiguity remains
explicit; no carrier correction or position estimate is adopted by this pilot.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_cross_RX_gain_prediction import fit,predict
from ds23_fractional_differential_phase import fractional_geometry
from ds23_conditional_pilot_components import component_segments
from ds23_differential_frame_phase import unique_frame_intersections
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_cross_RX_gain_prediction_v2'
BULK=Path('/srv/bulk/leo/research/ds23-cross-RX-gain-prediction-v2-20261021')
SOURCE=ROOT/'reports/2026_10_19_algo03_joint_frame_phase_fractional/results.json'
PANEL_AUTHORITY=ROOT/'reports/2026_10_19_algo03_cross_receiver_carrier/protocol.json'


def projected_gains(coefficients,covariance,train):
    c,cov=np.asarray(coefficients),np.asarray(covariance);train=np.asarray(train,bool)
    if c.ndim!=2 or train.shape!=(len(c),) or cov.shape!=(len(c),c.shape[1],c.shape[1]) or train.sum()<4:
        raise ValueError('matching frame channels and at least four training frames required')
    _,singular,vh=np.linalg.svd(c[train],full_matrices=False);direction=vh[0].conj()
    gain=c@direction;variance=np.einsum('i,nij,j->n',direction.conj(),cov,direction).real
    if np.any(variance<=0):raise ValueError('positive frame-channel extraction variance required')
    return dict(gain=gain,variance=variance,training_rank_one_fraction=float(singular[0]**2/sum(singular**2)))


def extract(values,entry,fits):
    fs=entry['sample_rate_hz'];samples=[values[:,rx,0].astype(float)+1j*values[:,rx,1] for rx in [0,1]]
    geometries=[fractional_geometry(y,fs,entry['edge'],entry['epochs'][rx],fits[rx]) for rx,y in enumerate(samples)]
    segments=unique_frame_intersections(*geometries,component_segments(*geometries))
    if len(segments)<10:raise ValueError('ten distinct matched frame pairs required')
    result={}
    for mode in ['flat','per_tone']:
        receivers=[]
        for rx,(y,g) in enumerate(zip(samples,geometries,strict=True)):
            columns=g['exact'].sum(axis=1,keepdims=True) if mode=='flat' else g['exact']
            design=np.column_stack((columns,np.ones(len(y))))
            coefficients=[];covariances=[]
            for ix in segments:
                x=design[ix];c,_,rank,_=np.linalg.lstsq(x,y[ix],rcond=1e-8)
                if rank!=x.shape[1]:raise ValueError('per-receiver channel design lost rank')
                residual=y[ix]-x@c;noise=float(np.vdot(residual,residual).real/(len(ix)-rank))
                coefficients.append(c[:-1]);covariances.append((noise*np.linalg.inv(x.conj().T@x))[:-1,:-1])
            receivers.append(dict(coefficients=np.asarray(coefficients),covariance=np.asarray(covariances)))
        result[mode]=receivers
    return dict(time_s=np.array([ix.mean()/fs for ix in segments]),modes=result,
        frame_pairs=[[int(geometries[0]['frame'][ix[0]]),int(geometries[1]['frame'][ix[0]])] for ix in segments])


def evaluate(times,a,b,va,vb,train):
    test=~train
    shared=fit(times[train],a[train],b[train],va[train],vb[train],shared=True)
    independent=fit(times[train],a[train],b[train],va[train],vb[train],shared=False)
    first=predict(shared,times[test],a[test],b[test],va[test],vb[test])
    second=predict(independent,times[test],a[test],b[test],va[test],vb[test])
    return dict(shared=shared,independent=independent,held_target_points=int(test.sum()),
        shared_held_NLL=first,independent_held_NLL=second,held_gain=second-first)


def one(job):
    index=job['index'];row=job['row'];entry=row['entry'];target=BULK/(f'probe{index:03d}.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second saved-IQ receiver-gain pilot cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:
        with np.load(ROOT/entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
        extraction=extract(values,entry,row['within_frame_fits']);times=extraction['time_s'];frames=np.arange(len(times));results={}
        for mode,receivers in extraction['modes'].items():
            folds=[]
            for parity in [0,1]:
                train=frames%2==parity
                gains=[projected_gains(r['coefficients'],r['covariance'],train) for r in receivers]
                a,b=gains[0]['gain'],gains[1]['gain'];va,vb=gains[0]['variance'],gains[1]['variance']
                actual=evaluate(times,a,b,va,vb,train);rng=np.random.default_rng(2026102130+index*2+parity);null=[]
                for _ in range(31):
                    phases=rng.uniform(-np.pi,np.pi,len(times));surrogate=abs(b)*np.exp(1j*phases)
                    null.append(evaluate(times,a,surrogate,va,vb,train)['held_gain'])
                p=(1+sum(v>=actual['held_gain'] for v in null))/32
                folds.append(dict(parity=parity,actual=actual,phase_randomized_control_gains=null,
                    phase_randomization_rank=float(p),gains=gains))
            checks=dict(both_held_RX2_prediction_gains_positive=all(f['actual']['held_gain']>0 for f in folds),
                both_preliminary_phase_control_ranks_at_most_1_over32=all(f['phase_randomization_rank']<=1/32 for f in folds),
                both_optimizers_converged=all(f['actual'][m]['converged'] for f in folds for m in ['shared','independent']),
                both_shared_frequencies_interior=all(not f['actual']['shared']['boundary'] for f in folds))
            results[mode]=dict(folds=folds,checks=checks,candidate_for_independent_replication=all(checks.values()),
                only_preliminary31_controls_not_familywise_confirmed=True)
        result=dict(index=index,case=entry['case'],channel=entry['channel'],status='complete',entry=entry,
            results=results,extraction=extraction,conditioned_whole_probe_CFO_epoch_and_rate_unchanged=True,
            all_channel_shapes_and_clock_parameters_trained_without_target_held_frames=True,
            no_individual_TX_phase_continuity_assumption=True,frequency_ambiguity_750Hz_unresolved=True,
            no_CFO_measurement_or_radio_calibration_or_position_change=True)
        # Keep complex scientific arrays explicit in the JSON research receipt.
        for records in extraction['modes'].values():
            for record in records:
                for key in ['coefficients','covariance']:
                    value=record.pop(key);record[key+'_real']=value.real;record[key+'_imag']=value.imag
        for mode in results.values():
            for fold in mode['folds']:
                for gains in fold['gains']:
                    value=gains.pop('gain');gains['gain_real']=value.real;gains['gain_imag']=value.imag
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(index=index,case=entry['case'],status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result)
    print(index,result['status'],{m:r['checks'] for m,r in result.get('results',{}).items()},result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    authority=read(PANEL_AUTHORITY)
    for panel,digest in authority['panel_sha256'].items():
        if sha(ROOT/panel)!=digest:raise ValueError('old saved dual-RX panel changed')
    source=read(SOURCE);jobs=[dict(index=k,row=r) for k,r in enumerate(source['rows'])]
    protocol=dict(probes=len(jobs),jobs=jobs,workers=5,per_probe_seconds=120,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_cross_RX_gain_prediction.py']},
        source_old_scalar_phase_results_sha256=sha(SOURCE),source_panel_authority_sha256=sha(PANEL_AUTHORITY),
        no_new_RF_collection_or_raw_recording_export=True,no_GPS_TLE_or_satellite_identity_used=True,
        fixed_original_RF_CFO_epoch_and_code_rate_conditioned=True,
        models='independent target gain continuity versus conditional shared freely-changing complex transmitter gains',
        channel_shapes='flat or8 independent per-tone complex channel gains; SVD shape learned on training frames only',
        noise='both extraction variances plus training-only extra complex discrepancy variance',
        matched_frame_support_and_noise_aware_complex_predictive_densities=True,
        frequency_prior_SD_hz=100.,frequency_branch_period_hz=750.,phase_controls_per_fold=31,
        preliminary_candidates_only_no_CFO_or_position_adoption=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen paired receiver gain pilot changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:rows=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],
        candidates={m:[r['index'] for r in rows if r['status']=='complete' and r['results'][m]['candidate_for_independent_replication']] for m in ['flat','per_tone']},
        no_CFO_or_position_correction_adopted=True,protocol_sha256=sha(path)))


if __name__=='__main__':main()
