"""Scan-disjoint conditional RF replication on the19 prespecified saved probes."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from probe_ds23_paired_gain_controls import bidirectional
from probe_ds23_cross_RX_gain_prediction import extract
from ds23_joint_gain_controls import triple_segments,frame_coefficients
from ds23_fractional_differential_phase import fractional_geometry
from decoupled_pilot_clocks import ContinuousCoupledWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_paired_gain_replication'
BULK=Path('/srv/bulk/leo/research/ds23-paired-gain-replication-20261021')


def one(job):
    index=job['index'];entry=job['entry'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('180second paired-gain replication cap')));signal.alarm(180)
    try:
        with np.load(entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
        if 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest()!=entry['raw_window_sha256']:
            raise ValueError('native saved dual-RX window hash changed')
        fs=entry['sample_rate_hz'];samples=[values[:,rx,0].astype(float)+1j*values[:,rx,1] for rx in [0,1]]
        fits=[ContinuousCoupledWorkspace(y,fs,entry['edge'],entry['epochs'][rx]).fast_joint_fit(entry['peaks'][rx]['fractional_tracking_cfo_hz'])
            for rx,y in enumerate(samples)]
        extraction=extract(values,entry,fits);t=extraction['time_s'];r=extraction['modes']['flat']
        a,b=r[0]['coefficients'][:,0],r[1]['coefficients'][:,0]
        va,vb=r[0]['covariance'][:,0,0].real,r[1]['covariance'][:,0,0].real
        actual=bidirectional(t,a,b,va,vb);rng=np.random.default_rng(2026102150+index);controls=[]
        for _ in range(199):
            phases=rng.uniform(-np.pi,np.pi,len(t));c=bidirectional(t,a,abs(b)*np.exp(1j*phases),va,vb)
            controls.append(c['score'])
        rank=(1+sum(v>=actual['score'] for v in controls))/200
        raw=read(ROOT/'reports/2026_10_19_algo02_ds23_full'/entry['case']/'tracking.json');source=raw.get('source',raw)
        probe=next(p for p in source['probes'] if p['visit_index']==entry['visit_index'] and p['receiver_id']==1)
        period=fs/750;alternatives=[p for p in probe['candidates'] if p['passed_fractional_margin_gate'] and
            abs((p['integer_epoch_sample']+p['fractional_epoch_offset_samples']-entry['epochs'][0]+period/2)%period-period/2)>10]
        wrong=None
        if alternatives:
            peak=max(alternatives,key=lambda p:p['fractional_margin']);epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
            fit=ContinuousCoupledWorkspace(samples[1],fs,entry['edge'],epoch).fast_joint_fit(peak['fractional_tracking_cfo_hz'])
            g=[fractional_geometry(y,fs,entry['edge'],entry['epochs'][rx],fits[rx]) for rx,y in enumerate(samples)]
            g.append(fractional_geometry(samples[1],fs,entry['edge'],epoch,fit));segments=triple_segments(g)
            if len(segments)>=10:
                first,fc=frame_coefficients(samples[0],g[0]['exact'].sum(axis=1,keepdims=True),segments)
                targets,tc=frame_coefficients(samples[1],np.column_stack([z['exact'].sum(axis=1) for z in g[1:]]),segments)
                times=np.array([ix.mean()/fs for ix in segments]);matched=bidirectional(times,first[:,0],targets[:,0],fc[:,0,0].real,tc[:,0,0].real)
                mismatch=bidirectional(times,first[:,0],targets[:,1],fc[:,0,0].real,tc[:,1,1].real)
                wrong=dict(actual=matched,wrong_epoch=mismatch,matched_frames=len(times),native_peak=peak,fit=fit,
                    matched_same_IQ_sample_support=True)
            else:wrong=dict(insufficient_triple_frames=len(segments))
        result=dict(index=index,case=entry['case'],status='complete',entry=entry,fits=fits,
            time_s=t,source_gain_real=a.real,source_gain_imag=a.imag,source_variance=va,
            target_gain_real=b.real,target_gain_imag=b.imag,target_variance=vb,
            actual=actual,phase_controls=controls,phase_control_rank=rank,wrong_epoch_control=wrong,
            conditional_candidate=bool(actual['score']>0 and rank<=.01 and actual['all_optimizers_converged'] and actual['all_shared_frequencies_interior']),
            whole_probe_CFO_timing_rate_conditioned_not_training_only=True,
            no_new_CFO_uncertainty_radio_calibration_or_position_estimate_adopted=True)
    except Exception as exc:result=dict(index=index,case=entry['case'],status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(index,entry['case'],result['status'],result.get('conditional_candidate'),result.get('error'),flush=True)
    return result


def main():
    BULK.mkdir(exist_ok=True);inventory=read(OUT/'inventory.json');jobs=[dict(index=k,entry=r) for k,r in enumerate(inventory['selected'])]
    protocol=dict(jobs=jobs,workers=10,per_probe_seconds=180,inventory_sha256=sha(OUT/'inventory.json'),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_paired_gain_replication.py','probe_ds23_paired_gain_controls.py','ds23_joint_gain_controls.py']},
        native_selection_frozen_before_complex_gain_results=True,old_5_probe_cases_excluded=True,
        primary='minimum held conditional gain over2receiver directions and2frame parity folds',
        phase_controls_per_probe=199,individual_phase_control_candidates_are_not_familywise_confirmed_identities=True,
        wrong_epoch_target_components_fitted_jointly_on_same_samples=True,
        no_satellite_ID_GPS_TLE_new_RF_collection_CFO_measurement_or_position_used=True,
        whole_probe_RF_fits_conditioned_not_training_only=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('paired-gain replication protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=10) as pool:rows=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),
        completed=sum(r['status']=='complete' for r in rows),conditional_candidates=[r['case'] for r in rows if r.get('conditional_candidate')],
        no_calibrated_absolute_CFO_or750Hz_branch_resolution_or_localization_gain_established=True))


if __name__=='__main__':main()
