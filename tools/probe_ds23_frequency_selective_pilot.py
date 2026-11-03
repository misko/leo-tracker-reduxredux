"""Bounded saved-IQ channel-model comparison with disjoint symbol prediction.

Condition on the same previously fitted epoch and code rate for both models.
No orbit, satellite labels, geographic target, or new recording is used.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import time
import numpy as np

from frequency_selective_pilot import ChannelPilotWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_frequency_selective_pilot'
SOURCE=ROOT/'reports/2026_10_19_ds23_raw_pilot_refinement'
CASES=('DS23-0202','DS23-0274')


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);jobs=[];bindings={}
    for case in CASES:
        result=SOURCE/(case+'_tracks.json');data=read(result)
        panel=SOURCE/(case+'_tracks_panel.npz')
        if sha(panel)!=data['panel_sha256']:raise ValueError('archived IQ panel changed')
        bindings[case]=dict(result_sha256=sha(result),panel_sha256=sha(panel))
        lookup={r['point']['observation_id']:r for r in data['rows']}
        for track in data['panel_metadata']['tracks']:
            ids=track['observation_ids']
            for k in sorted({0,len(ids)//2,len(ids)-1}):
                row=lookup[ids[k]]
                jobs.append(dict(case=case,observation_id=ids[k],track=track['key'],row=row))
    protocol=dict(jobs=jobs,bindings=bindings,workers=4,per_point_seconds=120,
        selection='First, middle and last original point of each of seven previously frozen complete curved tracks',
        frequency_radius_hz=120,epoch_and_code_rate='same previously fitted all-frame RF values in both models',
        channel_models=['one complex gain per frame','eight complex tone gains per frame'],
        independent_DC_per_frame=True,frame_phases_independent=True,
        heldout='Each CFO/channel fit uses one symbol parity; its channel coefficients predict the other parity. Epoch/rate are shared RF estimates, not independently cross-fitted.',
        no_GPS_TLE_or_satellite_input=True,new_RF_collection=False,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/frequency_selective_pilot.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('frequency selective RF protocol changed')
    if not target.exists():write(target,protocol)
    return protocol


def run(job):
    case=job['case'];oid=job['observation_id'];path=OUT/(case+'_'+oid.split(':')[-1]+'.json')
    if path.exists():return read(path)
    start=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second saved-IQ channel comparison budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    output=dict(case=case,observation_id=oid,track=job['track'])
    try:
        row=job['row'];point=row['point']
        with np.load(SOURCE/(case+'_tracks_panel.npz'),allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
            values=z[point['window_key']][:,point['receiver_offset']]
        y=values[:,0].astype(float)+1j*values[:,1].astype(float)
        peak=point['peak'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        workspace=ChannelPilotWorkspace(y,fs,point['edge'],epoch)
        old=row['joint_CFO_epoch_rate'];offset=old['offset_samples'];ppm=old['modulation_ppm'];center=old['CFO_hz']
        results={}
        for name,flat in [('flat',True),('per_tone',False)]:
            fits={subset:workspace.frequency_fit(center,offset,ppm,subset,flat=flat) for subset in ('all','symbol_even','symbol_odd')}
            prediction={subset:workspace.prediction_error(fits[subset],subset,flat=flat) for subset in ('symbol_even','symbol_odd')}
            control=float(workspace.evaluate([fits['all']['CFO_hz']],offset,ppm,control=True,flat=flat)[0])
            results[name]=dict(fits=fits,heldout=prediction,
                summed_heldout_squared_error=sum(r['heldout_squared_error'] for r in prediction.values()),
                control_score=control,exact_control_margin=fits['all']['score']-control,
                symbol_split_CFO_difference_hz=fits['symbol_even']['CFO_hz']-fits['symbol_odd']['CFO_hz'])
        f,g=results['flat'],results['per_tone']
        output.update(status='complete',results=results,receiver=point['receiver_id'],channel=point['channel'],
            CFO_change_from_flat_hz=g['fits']['all']['CFO_hz']-f['fits']['all']['CFO_hz'],
            heldout_relative_error_change=g['summed_heldout_squared_error']/f['summed_heldout_squared_error']-1,
            previous_flat_CFO_hz=center,archived_CFO_hz=row['archived_CFO_hz'],
            no_GPS_or_TLE_used=True,channel_comparison_conditioned_on_same_RF_timing_and_code_rate=True,
            all_original_RF_observations_retained=True)
    except Exception as exc:output.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    output['seconds']=time.monotonic()-start;write(path,output)
    print(case,job['track'],output['status'],output.get('error'),output.get('heldout_relative_error_change'),output.get('CFO_change_from_flat_hz'),flush=True)
    return output


def main():
    protocol=prepare()
    rows=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,j) for j in protocol['jobs']]):
            rows.append(f.result());write(OUT/'progress.json',dict(complete=len(rows),total=len(protocol['jobs'])))
    complete=[r for r in rows if r['status']=='complete']
    summary={}
    for rx in (1,2):
        selected=[r for r in complete if r['receiver']==rx]
        summary[str(rx)]=dict(n=len(selected),
            heldout_improves=sum(r['heldout_relative_error_change']<0 for r in selected),
            median_relative_heldout_error_change=float(np.median([r['heldout_relative_error_change'] for r in selected])) if selected else None,
            median_absolute_split_CFO_difference_hz={name:float(np.median([abs(r['results'][name]['symbol_split_CFO_difference_hz']) for r in selected])) if selected else None for name in ('flat','per_tone')},
            boundary_points=sum(any(f['frequency_search_boundary'] for f in r['results']['per_tone']['fits'].values()) for r in selected))
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,protocol_sha256=sha(OUT/'protocol.json'),
        failures=[r for r in rows if r['status']!='complete'],real_DS23_accuracy_gain=False,
        heldout_RF_prediction_is_not_proof_of_accurate_absolute_CFO=True))
    print('RF_CHANNEL_COMPARISON',summary,flush=True)


if __name__=='__main__':main()
