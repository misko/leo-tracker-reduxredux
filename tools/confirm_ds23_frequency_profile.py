"""Point-disjoint middle-probe confirmation of saved-IQ frequency profiles."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import numpy as np
import validate_ds23_frequency_profile as inference
from ds23_joint_component_refinement import JointComponentWorkspace
from probe_ds23_differential_frame_phase import jobs as archived_jobs
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_frequency_profile_confirmation'
BULK=Path('/srv/bulk/leo/research/ds23-frequency-profile-confirmation-20261021')
ORIGINAL_ONE=inference.one


def jobs():
    pilot=read(inference.SOURCE/'protocol.json')['jobs'];occupied={(r['job']['case'],r['job']['probe']) for r in pilot}
    chosen={r['job']['case']:r['job']['group'] for r in pilot}
    result=[r for r in archived_jobs() if chosen.get(r['job']['case'])==r['job']['group']
        and (r['job']['case'],r['job']['probe']) not in occupied]
    if len(result)!=23 or len({r['job']['case'] for r in result})!=23:raise ValueError('one distinct middle probe per original scan required')
    return result


def one(item):
    j=item['job'];target=BULK/(j['group']+f"_probe{j['probe']:06d}.json")
    if target.exists():return read(target)
    try:
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('30-second seed refinement cap exhausted')));signal.alarm(30)
        with np.load(Path(item['source'])/'panels'/(j['case']+'.npz'),allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==j['probe'])
            v=z[point['window_key']][:,point['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float)
        p=JointComponentWorkspace(y,metadata['sample_rate_hz'],j['edge'],[j['first']['epoch'],j['second']['epoch']],
            [item['fit']['first_fit'],item['fit']['second_fit']]);full=p.optimize();signal.alarm(0)
        record=ORIGINAL_ONE(item,dict(full=full));record['whole_probe_seed_fit']=full
        record['whole_probe_seed_interior']=not full['boundary'];write(target,record);return record
    except Exception as exc:
        record=dict(case=j['case'],group=j['group'],probe=j['probe'],status='failed',error=repr(exc));write(target,record);return record
    finally:signal.alarm(0)


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);selected=jobs()
    bindings=read(ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json')
    for panel in {Path(r['source'])/'panels'/(r['job']['case']+'.npz') for r in selected}:
        if sha(panel)!=bindings['saved_panel_sha256'][str(panel)]:raise ValueError('saved native panel changed')
    protocol=dict(jobs=selected,workers=8,middle_probes_disjoint_from_original46=True,
        same23_scans_not_scan_or_location_disjoint=True,RF_selection='one middle original qualified native-pair probe per scan',
        same_symbol_prediction_fit_and_qualification_rules_as_development=True,
        original_whole_probe_seed_fit_interior_stratum_also_disclosed=True,
        no_GPS_TLE_satellite_selection_or_new_RF=True,no_CFO_or_position_correction=True,
        development_sha256=sha(inference.OUT/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/validate_ds23_frequency_profile.py',
            ROOT/'tools/ds23_probe_frequency_profile.py',ROOT/'tools/ds23_joint_component_refinement.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('middle-probe RF confirmation changed')
    if not path.exists():write(path,protocol)
    inference.OUT,inference.BULK=OUT,BULK
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,item) for item in selected])]
    complete=[r for r in rows if r['status']=='complete'];clean=[r for r in complete if r['whole_probe_seed_interior']]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,complete=len(complete),
        both_folds_predict_better=sum(r['checks']['both_symbol_folds_predict_better'] for r in complete),
        RF_qualified=sum(r['RF_profile_qualified'] for r in complete),
        interior_seed_probes=len(clean),interior_seed_RF_qualified=sum(r['RF_profile_qualified'] for r in clean),
        median_heldout_profile_gain=float(np.median([f['heldout_profile_gain'] for r in complete for f in r['folds']])),
        no_absolute_frequency_or_position_adoption=True,not_independent_scan_or_location_generalization=True,
        source_protocol_sha256=sha(path)))
    print('MIDDLE_PROBE_CONFIRMATION',len(complete),'RFqualified',sum(r['RF_profile_qualified'] for r in complete),
        'both predictive',sum(r['checks']['both_symbol_folds_predict_better'] for r in complete),flush=True)


if __name__=='__main__':main()
