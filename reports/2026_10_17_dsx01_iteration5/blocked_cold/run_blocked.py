"""One authorized public production interpolation pilot, alternating20s parity0."""
import argparse
import csv
import inspect
import json
from pathlib import Path
import unittest
import numpy as np
from derive_blocks import derive_blocks,perturb_excluded,payload,digest
from leo.cli import shared_fast_position as pipeline
from leo.application import shared_fast_position as application
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.operations.tle_archive import TleArchiveReader

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
ATTEMPT=HERE/'S03-block20-parity0'
TLE_ROOT=Path('/var/lib/leo/tle')


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(application.plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def run(*,launch=False):
    if ATTEMPT.exists():raise FileExistsError('Prepared attempt namespace exists; no automatic retry')
    import test_blocks
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_blocks))
    if not tests.wasSuccessful():raise AssertionError('Prelaunch split tests failed')
    source=next(s for s in json.loads((DATA/'sources.json').read_text()) if s['source_id']=='S03')
    job,document,_,_=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2').plot_evidence(source['job_id'])
    if job['input_sha256']!=source['tracking_input_sha256'] or job['terminal']['sha256']!=source['terminal_sha256']:
        raise ValueError('Frozen source input binding differs')
    training,receipt=derive_blocks(document,block_seconds=20,training_parity=0)
    invariant,other=derive_blocks(perturb_excluded(document,receipt),block_seconds=20,training_parity=0)
    encoded=payload(training)
    assert encoded==payload(invariant) and receipt==other
    prepared,nodes=application.prepare_views(pipeline.load_input(training))
    alternate,_=application.prepare_views(pipeline.load_input(invariant))
    for view in ['all','low','high']:
        assert prepared[view].evidence_sha256==alternate[view].evidence_sha256
    policy='generic-cold24-shape3-fresh-six-ab-v1'
    if application.POLICY['source_generation_policy']!=policy or pipeline.run.__module__!='leo.cli.shared_fast_position':
        raise ValueError('Unmodified original public policy/entrypoint required')
    archive=TleArchiveReader(TLE_ROOT);cutoff=prepared['all'].start_utc_ns-505_000_000_000
    snapshot=archive.select_latest_before(cutoff);tle=archive.read(snapshot)
    assert snapshot.collected_utc_ns<cutoff
    # Fixed evaluation denominator accounting uses IDs/metadata only.
    roles={m['global_group_id']:m['role'] for m in receipt['membership']}
    frozen=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    frozen=[dict(source_id=r['source_id'],observation_id=r['observation_id'],time_s=r['time_s']) for r in frozen]
    full=[r for r in frozen if r['source_id']=='S03']
    assert all(r['observation_id'] in roles for r in full)
    evaluation_roles={role:sum(roles[r['observation_id']]==role for r in full) for role in ['train','held','boundary']}
    assert set(prepared['all'].observations.window_ids)=={r['observation_id'] for r in full if roles[r['observation_id']]=='train'}
    with (DATA/'membership.csv').open() as stream:members=list(csv.DictReader(stream))
    own=[m for m in members if m['source_id']=='S03']
    windows=[]
    for rid in sorted(set(m['region_id'] for m in own)):
        keys=[m['observation_id'] for m in own if m['region_id']==rid]
        windows.append(dict(region_id=rid,observations=len(keys),**{role:sum(roles[k]==role for k in keys) for role in ['train','held','boundary']}))
    denom=dict(frozen_all_observations=len(frozen),frozen_challenge_observations=len(members),
        pilot_source_observations=len(full),pilot_source_challenge=len(own),
        other_source_observations_untested=len(frozen)-len(full),other_source_challenge_untested=len(members)-len(own),
        pilot_membership=evaluation_roles,challenge_membership={role:sum(roles[m['observation_id']]==role for m in own) for role in ['train','held','boundary']},windows=windows)
    receipt.update(source_id='S03',parent_job_id=source['job_id'],parent_input_sha256=source['tracking_input_sha256'],
        parent_terminal_sha256=source['terminal_sha256'],derived_input_sha256=digest(encoded),
        held_cfo_score_gate_invariance_of_training_bytes_and_preparation=True,
        prelaunch_tests=dict(run=tests.testsRun,errors=len(tests.errors),failures=len(tests.failures)),
        training_views={name:dict(observations=len(p.observations.times_s),minimum_s=float(p.observations.times_s.min()),
            maximum_s=float(p.observations.times_s.max()),bootstrap_tracks=len(p.bootstrap_tracks),evidence_sha256=p.evidence_sha256) for name,p in prepared.items()},
        clock_nodes_s=nodes,training_window_ids=prepared['all'].observations.window_ids,evaluation_denominators=denom,
        causal_tle=dict(sha256=snapshot.digest,provider=snapshot.provider,collected_utc_ns=snapshot.collected_utc_ns,
            strict_cutoff_utc_ns=cutoff,payload_sha256=digest(tle.encode('utf-8'))),
        exact_policy=application.POLICY,maximum_whole_run_seconds=480,launch_requested=launch,
        public_entrypoint='leo.cli.shared_fast_position.run(input_path,output,maximum_seconds=480,tle_root)',
        source_code_sha256={str(Path(inspect.getsourcefile(m))):digest(Path(inspect.getsourcefile(m)).read_bytes()) for m in [pipeline,application]},
        research_code_sha256={p.name:digest(p.read_bytes()) for p in [HERE/'derive_blocks.py',HERE/'test_blocks.py',HERE/'run_blocked.py']},
        scope='Deterministic S03 parity0 alternating20s gap interpolation, selected before observing outcomes. '
        'Fresh TRAIN-only original production discovery; no full-fit bank, position or calibration seed. Fittedc throughout source generation; any downstream c0 control is conditional.')
    ATTEMPT.mkdir(parents=True)
    with (ATTEMPT/'training-input.json').open('xb') as stream:stream.write(encoded)
    save(ATTEMPT/'derivation.json',receipt)
    print(json.dumps(dict(stage='preflight_passed',derived_input_sha256=receipt['derived_input_sha256'],
        probes=dict(train=receipt['training_probe_groups'],held=receipt['held_probe_groups'],boundary=receipt['boundary_probe_groups']),
        evaluation_denominators=denom,clock_nodes_s=nodes.tolist(),tle=receipt['causal_tle'],launch_requested=launch)),flush=True)
    if not launch:return
    result=pipeline.run(ATTEMPT/'training-input.json',ATTEMPT/'output',maximum_seconds=480,tle_root=TLE_ROOT)
    if result.get('provenance',{}).get('tle_sha256',snapshot.digest)!=snapshot.digest:raise ValueError('Causal archive selection changed during launch')
    print(json.dumps(dict(stage='terminal',state=result['state'],reason=result.get('reason'),
        elapsed_seconds=result['elapsed_seconds'],selection=result.get('selection'))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true')
    args=parser.parse_args();run(launch=args.run)
