"""Supplement exploratory phase proposals with held-out RF carrier prediction."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import numpy as np

from ds23_sign_carrier_prediction import within_frame_carrier_prediction
from local_pilot_refinement import PilotWorkspace
from probe_ds23_sign_aware_pilot import OUT as SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_sign_carrier_validation'


def run(job,record):
    p=job['point']
    with np.load(ROOT/job['panel'],allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz'];v=z[p['window_key']][:,p['receiver_offset']]
    epoch=p['peak']['integer_epoch_sample']+p['peak']['fractional_epoch_offset_samples']
    workspace=PilotWorkspace(v[:,0].astype(float)+1j*v[:,1].astype(float),fs,p['edge'],epoch)
    guard=within_frame_carrier_prediction(workspace,record['base_fit'],record['result'])
    return dict(record,within_frame_carrier_prediction=guard,
        phase_proposal_accepted=record['result']['accepted'],accepted=record['result']['accepted'] and guard['passed'])


def main():
    original=read(SOURCE/'protocol.json');evaluation=read(SOURCE/'evaluation.json')
    if evaluation['protocol_sha256']!=sha(SOURCE/'protocol.json'):raise ValueError('source RF protocol changed')
    for name,expected in original['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('source RF inference changed')
    for path,expected in original['panels'].items():
        if sha(ROOT/path)!=expected:raise ValueError('saved IQ changed')
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(source_evaluation_sha256=sha(SOURCE/'evaluation.json'),
        source_protocol_sha256=sha(SOURCE/'protocol.json'),maximum_heldout_intraframe_profile_loss=9.,
        test_all_original_development_and_point_disjoint_confirmation_probes=True,
        both_candidate_CFOs_estimated_on_training_frames=True,
        within_frame_unknown_complex_gains_profiled_identically=True,
        all_phase_proposal_checks_retained=True,no_GPS_TLE_or_position_input=True,
        position_not_yet_modified=True,workers=4,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_sign_carrier_prediction.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('carrier validation protocol changed')
    if not target.exists():write(target,protocol)
    lookup={r['observation_id']:r for r in evaluation['rows']}
    rows=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,j,lookup[j['point']['observation_id']]) for j in original['jobs']]):rows.append(f.result())
    summary={}
    for s in ('development','point_disjoint_confirmation'):
        rr=[r for r in rows if r['stratum']==s]
        summary[s]=dict(n=len(rr),phase_proposals=sum(r['phase_proposal_accepted'] for r in rr),
            accepted=sum(r['accepted'] for r in rr),
            phase_proposals_rejected_by_actual_carrier=sum(r['phase_proposal_accepted'] and not r['within_frame_carrier_prediction']['passed'] for r in rr))
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,protocol_sha256=sha(target),real_DS23_accuracy_gain=False))
    print('WITHIN_FRAME_CARRIER_VALIDATION',summary,flush=True)


if __name__=='__main__':main()
