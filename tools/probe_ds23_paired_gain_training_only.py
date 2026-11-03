"""Same-sample whole-probe versus training-only RF nuisance ablation."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_training_gain_rf import restricted_workspace
from ds23_fractional_differential_phase import fractional_geometry
from ds23_conditional_pilot_components import component_segments
from ds23_differential_frame_phase import unique_frame_intersections
from ds23_joint_gain_controls import frame_coefficients
from probe_ds23_cross_RX_gain_prediction import evaluate
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_paired_gain_training_only'
BULK=Path('/srv/bulk/leo/research/ds23-paired-gain-training-only-20261021')
INVENTORY=ROOT/'reports/2026_10_21_ds23_paired_gain_replication/inventory.json'


def gains(samples,entry,epochs,fits,segments):
    results=[]
    for rx,y in enumerate(samples):
        geometry=fractional_geometry(y,entry['sample_rate_hz'],entry['edge'],epochs[rx],fits[rx])
        coefficient,covariance=frame_coefficients(y,geometry['exact'].sum(axis=1,keepdims=True),segments)
        results.append((coefficient[:,0],covariance[:,0,0].real))
    return results


def one(job):
    index=job['index'];entry=job['entry'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('180second train-only RF ablation cap')));signal.alarm(180)
    try:
        with np.load(entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
        if 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest()!=entry['raw_window_sha256']:raise ValueError('saved native window changed')
        fs=entry['sample_rate_hz'];samples=[values[:,rx,0].astype(float)+1j*values[:,rx,1] for rx in [0,1]]
        epochs=np.array(entry['epochs']);epochs[1]+=np.rint((epochs[0]-epochs[1])/(fs/750))*(fs/750)
        initial=[dict(CFO_hz=p['fractional_tracking_cfo_hz'],offset_samples=0.,modulation_ppm=0.) for p in entry['peaks']]
        geometry=[fractional_geometry(y,fs,entry['edge'],epochs[rx],initial[rx]) for rx,y in enumerate(samples)]
        common=unique_frame_intersections(*geometry,component_segments(*geometry))
        segments=[ix[16:-16] for ix in common if len(ix)>=112]
        if len(segments)<10:raise ValueError('ten frozen native frame intersections required')
        t=np.array([ix.mean()/fs for ix in segments]);frames=np.arange(len(t))
        full=[restricted_workspace(y,fs,entry['edge'],epochs[rx],segments).fast_joint_fit(initial[rx]['CFO_hz']) for rx,y in enumerate(samples)]
        full_gains=gains(samples,entry,epochs,full,segments);folds=[];null_scores=np.empty((199,4))
        rng=np.random.default_rng(2026102160+index);random_phases=rng.uniform(-np.pi,np.pi,(199,len(t)))
        for parity in [0,1]:
            train=frames%2==parity;training=[ix for k,ix in enumerate(segments) if train[k]]
            native_fits=[restricted_workspace(y,fs,entry['edge'],epochs[rx],training).fast_joint_fit(initial[rx]['CFO_hz']) for rx,y in enumerate(samples)]
            train_gain=gains(samples,entry,epochs,native_fits,segments)
            used=np.concatenate(training);held=np.concatenate([ix for k,ix in enumerate(segments) if not train[k]])
            if np.intersect1d(used,held).size:raise ValueError('held IQ samples entered RF training support')
            (a,va),(b,vb)=train_gain;records=[];controls=[]
            for direction in [0,1]:
                args=(a,b,va,vb) if direction==0 else (b,a,vb,va)
                actual=evaluate(t,*args,train)
                (ca,cva),(cb,cvb)=full_gains;whole=(ca,cb,cva,cvb) if direction==0 else (cb,ca,cvb,cva)
                whole_control=evaluate(t,*whole,train)
                records.append(dict(direction=direction,actual=actual,whole_probe_RF_control=whole_control))
                for k,phases in enumerate(random_phases):
                    changed=abs(b)*np.exp(1j*phases)
                    args=(a,changed,va,vb) if direction==0 else (changed,a,vb,va)
                    null_scores[k,2*parity+direction]=evaluate(t,*args,train)['held_gain']
            folds.append(dict(parity=parity,native_training_fits=native_fits,training_samples_per_RX=len(used),
                held_samples_per_RX=len(held),training_frame_indices=frames[train],records=records,
                held_samples_disjoint_from_all_native_RF_fitting=True,
                source_gain_real=a.real,source_gain_imag=a.imag,source_variance=va,
                target_gain_real=b.real,target_gain_imag=b.imag,target_variance=vb))
        actual_score=min(r['actual']['held_gain'] for f in folds for r in f['records'])
        whole_score=min(r['whole_probe_RF_control']['held_gain'] for f in folds for r in f['records'])
        null=null_scores.min(axis=1);rank=(1+int(sum(null>=actual_score)))/200
        converged=all(r['actual'][m]['converged'] for f in folds for r in f['records'] for m in ['shared','independent'])
        interior=all(not r['actual']['shared']['boundary'] for f in folds for r in f['records'])
        result=dict(index=index,case=entry['case'],status='complete',entry=entry,aligned_epochs=epochs,
            frames=len(t),time_s=t,folds=folds,whole_RF_fits=full,actual_score=float(actual_score),
            whole_probe_RF_control_score=float(whole_score),phase_control_scores=null,phase_control_rank=rank,
            conditional_candidate=bool(actual_score>0 and rank<=.01 and converged and interior),
            all_native_RF_and_gain_parameters_learned_without_target_held_IQ=True,
            fixed_native_acquisition_peaks_are_conditioned_initial_seeds_and_support_not_refit_from_held_samples=True,
            no750Hz_branch_resolution_CFO_precision_or_position_estimate_adopted=True)
    except Exception as exc:result=dict(index=index,case=entry['case'],status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(index,entry['case'],result['status'],result.get('actual_score'),result.get('conditional_candidate'),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);inventory=read(INVENTORY);jobs=[dict(index=k,entry=e) for k,e in enumerate(inventory['selected'])]
    protocol=dict(jobs=jobs,workers=10,per_probe_seconds=180,inventory_sha256=sha(INVENTORY),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_paired_gain_training_only.py','ds23_training_gain_rf.py','ds23_joint_gain_controls.py']},
        segmentation='native acquisition epoch only; freeze common frames then trim16samples from each boundary',
        native_CFO_epoch_offset_and_code_rate_refit_on_training_IQ_only=True,
        whole_probe_control_uses_identical_frozen_frame_samples=True,
        conditional_gain_primary='minimum held gain over both receiver directions and both frame folds',
        phase_controls=199,old_pilot_cases_excluded=True,individual_candidates_not_familywise_confirmed=True,
        coarse_native_GLRT_acquisition_is_conditioned_on_not_independent=True,
        no_new_RF_GPS_TLE_satellite_ID_CFO_measurement_or_position_gain=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('training-only RF protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=10) as pool:rows=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,conditional_candidates=[r['case'] for r in rows if r.get('conditional_candidate')],
        protocol_sha256=sha(path),no_CFO_uncertainty_or_position_improvement_established=True))


if __name__=='__main__':main()
