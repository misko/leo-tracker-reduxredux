"""Stronger bidirectional controls for the old conditional paired-gain pilot.

The primary flat-channel score is the minimum held prediction gain over both
receiver directions and both frame folds. Whole-probe RF fits remain conditioned
upon; no absolute frequency correction or localization measurement is adopted.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from probe_ds23_cross_RX_gain_prediction import evaluate
from run_algo01_ds23_sample import ROOT,read,write,sha

OLD=ROOT/'reports/2026_10_21_ds23_cross_RX_gain_prediction_v2'
OLD_BULK=Path('/srv/bulk/leo/research/ds23-cross-RX-gain-prediction-v2-20261021')
OUT=ROOT/'reports/2026_10_21_ds23_paired_gain_controls'
BULK=Path('/srv/bulk/leo/research/ds23-paired-gain-controls-20261021')


def decode(row):
    extraction=row['extraction'];receivers=extraction['modes']['flat']
    values=[]
    for r in receivers:
        c=np.asarray(r['coefficients_real'])+1j*np.asarray(r['coefficients_imag'])
        cov=np.asarray(r['covariance_real'])+1j*np.asarray(r['covariance_imag'])
        if c.shape[1]!=1:raise ValueError('primary channel model must have one complex coefficient')
        values.append((c[:,0],cov[:,0,0].real))
    return np.asarray(extraction['time_s']),values


def bidirectional(t,a,b,va,vb):
    records=[]
    for parity in [0,1]:
        train=np.arange(len(t))%2==parity
        for direction in ['RX1_to_RX2','RX2_to_RX1']:
            args=(a,b,va,vb) if direction=='RX1_to_RX2' else (b,a,vb,va)
            r=evaluate(t,*args,train)
            records.append(dict(direction=direction,parity=parity,**r))
    return dict(score=float(min(r['held_gain'] for r in records)),folds=records,
        all_optimizers_converged=all(r[k]['converged'] for r in records for k in ['shared','independent']),
        all_shared_frequencies_interior=all(not r['shared']['boundary'] for r in records))


def one(index):
    destination=BULK/f'probe{index:03d}.json'
    if destination.exists():return read(destination)
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('400second bidirectional-gain control budget')));signal.alarm(400)
    source=read(OLD_BULK/f'probe{index:03d}.json')
    try:
        t,values=decode(source);(a,va),(b,vb)=values
        actual=bidirectional(t,a,b,va,vb);rng=np.random.default_rng(2026102140+index)
        controls=[]
        for k in range(199):
            phases=rng.uniform(-np.pi,np.pi,len(t));surrogate=abs(b)*np.exp(1j*phases)
            result=bidirectional(t,a,surrogate,va,vb)
            controls.append(dict(index=k,score=result['score'],all_optimizers_converged=result['all_optimizers_converged']))
        rank=(1+sum(r['score']>=actual['score'] for r in controls))/200
        shifts=[]
        for shift in range(1,len(t)):
            r=bidirectional(t,a,np.roll(b,shift),va,np.roll(vb,shift))
            shifts.append(dict(shift=shift,score=r['score']))
        different=[]
        for other in range(5):
            if other==index:continue
            alt=read(OLD_BULK/f'probe{other:03d}.json')
            if (source['case'],source['entry']['rf_hz'])!=(alt['case'],alt['entry']['rf_hz']):continue
            other_t,other_values=decode(alt);other_b,other_vb=other_values[1]
            n=min(len(t),len(other_t));r=bidirectional(t[:n],a[:n],other_b[:n],va[:n],other_vb[:n])
            same=bidirectional(t[:n],a[:n],b[:n],va[:n],vb[:n])
            different.append(dict(other_index=other,score=r['score'],same_window_score_on_matched_frame_count=same['score'],
                matching_frame_count=n,support_is_different_physical_frames_not_a_randomized_p_value=True))
        qualifies=bool(actual['score']>0 and rank<=.01 and actual['all_optimizers_converged'] and actual['all_shared_frequencies_interior'])
        result=dict(index=index,case=source['case'],status='complete',actual=actual,
            phase_randomized_controls=controls,phase_control_rank=rank,
            familywise5_probe_primary_threshold=.01,conditional_primary_candidate=qualifies,
            circular_frame_controls=shifts,different_window_controls=different,
            source_sha256=sha(OLD_BULK/f'probe{index:03d}.json'),
            conditioned_whole_probe_CFO_epoch_and_code_rate_not_refitted_on_training=True,
            no_wrong_epoch_RF_control_or_new_probe_replication_claim=True,
            no_resolved750Hz_ambiguity_or_frequency_uncertainty_or_position_gain_claim=True)
    except Exception as exc:result=dict(index=index,case=source['case'],status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(destination,result)
    print(index,result['status'],result.get('phase_control_rank'),result.get('conditional_primary_candidate'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(probes=list(range(5)),workers=5,controls_per_probe=199,
        primary='flat channel; minimum held gain over2receiver directions and2parity folds',
        source_pilot_sha256=sha(OLD/'evaluation.json'),source_protocol_sha256=sha(OLD/'protocol.json'),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_paired_gain_controls.py','ds23_cross_RX_gain_prediction.py']},
        original_probe_sha256={i:sha(OLD_BULK/f'probe{i:03d}.json') for i in range(5)},
        old_data_reanalysis_not_independent_probe_replication=True,
        whole_probe_RF_fits_conditioned_not_training_only=True,
        no_new_RF_GPS_TLE_or_position_estimation=True,
        no_new_CFO_precision_or_radio_calibration_adopted=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('paired-gain control protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:rows=[f.result() for f in as_completed([pool.submit(one,i) for i in range(5)])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,
        conditional_candidates=[r['index'] for r in rows if r.get('conditional_primary_candidate')],
        no_position_algorithm_promoted=True,protocol_sha256=sha(path)))


if __name__=='__main__':main()
