"""Same-IQ, same-frame-support control of conditional cross-RX pilot gains."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_joint_gain_controls import triple_segments,frame_coefficients
from probe_ds23_paired_gain_controls import bidirectional
from probe_ds23_cross_RX_gain_prediction import SOURCE,PANEL_AUTHORITY
from ds23_fractional_differential_phase import fractional_geometry
from decoupled_pilot_clocks import ContinuousCoupledWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_wrong_epoch_gain_controls'
BULK=Path('/srv/bulk/leo/research/ds23-wrong-epoch-gain-controls-20261021')


def one(index):
    path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120second wrong-epoch gain control cap')));signal.alarm(120)
    row=read(SOURCE)['rows'][index];entry=row['entry'];fs=entry['sample_rate_hz']
    try:
        raw=read(ROOT/'reports/2026_10_19_algo02_ds23_full'/entry['case']/'tracking.json');source=raw.get('source',raw)
        probe=next(p for p in source['probes'] if p['visit_index']==entry['visit_index'] and p['receiver_id']==1)
        period=fs/750
        alternatives=[p for p in probe['candidates'] if p['passed_fractional_margin_gate'] and
            abs((p['integer_epoch_sample']+p['fractional_epoch_offset_samples']-entry['epochs'][0]+period/2)%period-period/2)>10]
        if not alternatives:
            result=dict(index=index,case=entry['case'],status='no_distinct_native_epoch')
        else:
            wrong=max(alternatives,key=lambda p:p['fractional_margin']);epoch=wrong['integer_epoch_sample']+wrong['fractional_epoch_offset_samples']
            with np.load(ROOT/entry['panel'],allow_pickle=False) as z:values=z[entry['window_key']]
            samples=[values[:,rx,0].astype(float)+1j*values[:,rx,1] for rx in [0,1]]
            ws=ContinuousCoupledWorkspace(samples[1],fs,entry['edge'],epoch);fit=ws.fast_joint_fit(wrong['fractional_tracking_cfo_hz'])
            g=[fractional_geometry(y,fs,entry['edge'],entry['epochs'][rx],row['within_frame_fits'][rx]) for rx,y in enumerate(samples)]
            g.append(fractional_geometry(samples[1],fs,entry['edge'],epoch,fit))
            segments=triple_segments(g)
            if len(segments)<10:raise ValueError('ten distinct triple-component frame intersections required')
            first,var_first=frame_coefficients(samples[0],g[0]['exact'].sum(axis=1,keepdims=True),segments)
            target_columns=np.column_stack([geometry['exact'].sum(axis=1) for geometry in g[1:]])
            target,target_cov=frame_coefficients(samples[1],target_columns,segments)
            times=np.array([ix.mean()/fs for ix in segments]);a=first[:,0];va=var_first[:,0,0].real
            actual=bidirectional(times,a,target[:,0],va,target_cov[:,0,0].real)
            control=bidirectional(times,a,target[:,1],va,target_cov[:,1,1].real)
            result=dict(index=index,case=entry['case'],status='complete',actual=actual,wrong_epoch=control,
                native_wrong_peak=wrong,wrong_whole_probe_fit=fit,matched_frames=len(times),
                source_frame_ids=[int(g[0]['frame'][s[0]]) for s in segments],
                same_sample_indices_for_both_target_components=True,
                source_gain_real=a.real,source_gain_imag=a.imag,source_variance=va,
                target_gain_real=target.real,target_gain_imag=target.imag,
                target_covariance_real=target_cov.real,target_covariance_imag=target_cov.imag,time_s=times,
                actual_shared_frequency_mod750_hz=[r['shared']['frequency_correction_mod750_hz'] for r in actual['folds']],
                actual_exceeds_wrong_epoch_score=actual['score']>control['score'],
                RF_models_condition_on_whole_probe_CFO_timing_rate=True,
                no_satellite_identity_frequency_precision_or_position_gain_established=True)
    except Exception as exc:result=dict(index=index,case=entry['case'],status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(index,result['status'],result.get('actual',{}).get('score'),result.get('wrong_epoch',{}).get('score'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    authority=read(PANEL_AUTHORITY)
    for name,digest in authority['panel_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('saved dual-RX panel changed')
    protocol=dict(probes=list(range(5)),workers=5,
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_wrong_epoch_gain_controls.py','ds23_joint_gain_controls.py','probe_ds23_paired_gain_controls.py']},
        source_old_RF_sha256=sha(SOURCE),panel_authority_sha256=sha(PANEL_AUTHORITY),
        selection='highest-margin different native RX2 epoch; no outcome-dependent peak choice',
        matching='one distinct source/actual-target/wrong-target frame each; common IQ indices',
        target_model='joint actual+wrong complex gains plus DC per frame, full coefficient covariance retained',
        whole_probe_RF_parameters_conditioned_not_training_only=True,
        no_GPS_TLE_satellite_ID_or_new_RF_collection=True,no_new_CFO_or_position_measurement_adopted=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('wrong-epoch control protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:rows=[f.result() for f in as_completed([pool.submit(one,i) for i in range(5)])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path)))


if __name__=='__main__':main()
