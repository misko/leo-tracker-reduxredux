"""Replay the saved per-tone/flat scores and disjoint-symbol prediction SSE."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import numpy as np

from frequency_selective_pilot import ChannelPilotWorkspace
from probe_ds23_frequency_selective_pilot import OUT,SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay(job,record):
    point=job['row']['point'];case=job['case']
    with np.load(SOURCE/(case+'_tracks_panel.npz'),allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
        raw=z[point['window_key']][:,point['receiver_offset']]
    peak=point['peak'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
    p=ChannelPilotWorkspace(raw[:,0].astype(float)+1j*raw[:,1].astype(float),fs,point['edge'],epoch)
    maximum_score=maximum_prediction=0.
    for name,flat in [('flat',True),('per_tone',False)]:
        r=record['results'][name]
        for subset,fit in r['fits'].items():
            score=float(p.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],subset,flat=flat)[0])
            maximum_score=max(maximum_score,abs(score-fit['score']))
            if subset in r['heldout']:
                prediction=p.prediction_error(fit,subset,flat=flat)
                old=r['heldout'][subset]['heldout_squared_error']
                maximum_prediction=max(maximum_prediction,abs(prediction['heldout_squared_error']-old)/max(1.,abs(old)))
        fit=r['fits']['all']
        control=float(p.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],control=True,flat=flat)[0])
        maximum_score=max(maximum_score,abs(control-r['control_score']))
    if maximum_score>1e-10 or maximum_prediction>1e-10:raise ValueError('RF score/prediction replay mismatch')
    return dict(case=case,observation_id=job['observation_id'],maximum_score_difference=maximum_score,
        maximum_relative_prediction_SSE_difference=maximum_prediction,receiver=record['receiver'])


def main():
    protocol=read(OUT/'protocol.json');corrected=read(OUT/'corrected_evaluation.json')
    if corrected['source_evaluation_sha256']!=sha(OUT/'evaluation.json'):raise ValueError('corrected RF evaluation source changed')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('RF inference source changed')
    lookup={r['observation_id']:r for r in corrected['rows']}
    rows=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(replay,j,lookup[j['observation_id']]) for j in protocol['jobs']]):rows.append(f.result())
    write(OUT/'independent_replay_audit.json',dict(rows=rows,probes_replayed=len(rows),
        maximum_score_difference=max(r['maximum_score_difference'] for r in rows),
        maximum_relative_prediction_SSE_difference=max(r['maximum_relative_prediction_SSE_difference'] for r in rows),
        corrected_evaluation_sha256=sha(OUT/'corrected_evaluation.json'),audit_source_sha256=sha(Path(__file__)),
        RF_endpoints_replayed_not_refitted=True,real_DS23_accuracy_gain=False))
    print('RF_CHANNEL_REPLAY_COMPLETE',len(rows),'probes',flush=True)


if __name__=='__main__':main()
