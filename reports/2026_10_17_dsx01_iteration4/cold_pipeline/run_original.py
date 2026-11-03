"""One true-half, unmodified original production replay; no RF or publication."""
import argparse
from dataclasses import asdict
import inspect
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from derive import temporal_half,perturb_excluded,payload,digest
from leo.cli import shared_fast_position as pipeline
from leo.application import shared_fast_position as application
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.operations.tle_archive import TleArchiveReader

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
ATTEMPT=HERE/'S03-early_to_late'
TLE_ROOT=Path('/var/lib/leo/tle')


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(application.plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def run(*,launch=False):
    if ATTEMPT.exists():raise FileExistsError('Preparation/attempt already exists; never silently retry or overwrite')
    import test_cold_pipeline
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_cold_pipeline))
    if not tests.wasSuccessful():raise AssertionError('Prelaunch unit tests failed')
    source=next(s for s in json.loads((REPORTS/'2026_10_16_dsx01_fast_association_losses'/'sources.json').read_text()) if s['source_id']=='S03')
    job,document,terminal,_=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2').plot_evidence(source['job_id'])
    if (job['input_sha256']!=source['tracking_input_sha256'] or job['terminal']['sha256']!=source['terminal_sha256']):
        raise ValueError('Frozen parent input receipt changed')
    derived,receipt=temporal_half(document,direction='early_to_late')
    altered=perturb_excluded(document,receipt)
    invariant,other=temporal_half(altered,direction='early_to_late')
    training_bytes=payload(derived)
    if training_bytes!=payload(invariant) or receipt!=other:raise AssertionError('Held candidate leakage')
    train_source=pipeline.load_input(derived)
    prepared,nodes=application.prepare_views(train_source)
    same,_=application.prepare_views(pipeline.load_input(invariant))
    for view in ['all','low','high']:
        if prepared[view].evidence_sha256!=same[view].evidence_sha256:
            raise AssertionError('Held candidate perturbation changed training preparation')
        if prepared[view].observations.times_s.max()>receipt['cut_s']:
            raise AssertionError('Retained candidate support center escaped training half')
    if application.POLICY['source_generation_policy']!='generic-cold24-shape3-fresh-six-ab-v1':
        raise ValueError('Original source generation policy changed; do not approximate')
    if pipeline.run.__module__!='leo.cli.shared_fast_position':raise ValueError('Public original entrypoint replaced')
    cutoff=prepared['all'].start_utc_ns-505_000_000_000
    archive=TleArchiveReader(TLE_ROOT);snapshot=archive.select_latest_before(cutoff)
    tle=archive.read(snapshot)
    if snapshot.collected_utc_ns>=cutoff:raise ValueError('Noncausal public snapshot')
    receipt.update(source_id='S03',parent_job_id=source['job_id'],
        parent_input_sha256=source['tracking_input_sha256'],
        parent_terminal_binding_sha256=source['terminal_sha256'],
        parent_document_provenance_sha256=digest(payload(document.get('provenance',{}))),
        derived_input_sha256=digest(training_bytes),
        training_bytes_and_preparation_invariant_to_every_excluded_cfo_score_and_gate=True,
        prelaunch_tests=dict(run=tests.testsRun,failures=len(tests.failures),errors=len(tests.errors)),
        training_views={view:dict(observations=len(p.observations.times_s),
            minimum_s=float(p.observations.times_s.min()),maximum_s=float(p.observations.times_s.max()),
            bootstrap_tracks=len(p.bootstrap_tracks),evidence_sha256=p.evidence_sha256)
            for view,p in prepared.items()},
        training_clock_nodes_s=nodes,training_window_ids=prepared['all'].observations.window_ids,
        causal_tle=dict(sha256=snapshot.digest,provider=snapshot.provider,
            collected_utc_ns=snapshot.collected_utc_ns,strict_cutoff_utc_ns=cutoff,
            payload_sha256=digest(tle.encode('utf-8')),
            policy='Unmodified public latest snapshot strictly before origin minus505seconds; both providers eligible'),
        exact_policy=application.POLICY,maximum_whole_run_seconds=480,launch_requested=launch,
        public_entrypoint='leo.cli.shared_fast_position.run(input_path,output,maximum_seconds=480,tle_root)',
        source_code_sha256={str(Path(inspect.getsourcefile(module))):digest(Path(inspect.getsourcefile(module)).read_bytes())
            for module in [pipeline,application]},
        research_code_sha256={p.name:digest(p.read_bytes()) for p in [HERE/'derive.py',HERE/'clock_transport.py',HERE/'run_original.py',HERE/'test_cold_pipeline.py']},
        bank_policy='Fresh TRAIN-only discovery/eligibility/selected bank; no saved full-recording bank or model state enters inference.',
        c_policy='Original production pipeline fits c throughout; no whole-pipeline c0 arm is claimed. A future downstream c0 continuation would be conditional.',
        held_prediction_policy='Only train-selected IDs propagated on full known metadata. Residual clock is extended constantly at trained boundaries while learned affine slopes remain; no held knots fitted.')
    ATTEMPT.mkdir(parents=True)
    with (ATTEMPT/'training-input.json').open('xb') as stream:stream.write(training_bytes)
    save(ATTEMPT/'derivation.json',receipt)
    print(json.dumps(dict(stage='preflight_passed',training_input=str(ATTEMPT/'training-input.json'),
        derived_input_sha256=receipt['derived_input_sha256'],train_probes=receipt['training_probe_groups'],
        excluded_probes=receipt['held_probe_groups']+receipt['boundary_probe_groups'],
        training_windows=receipt['training_views']['all']['observations'],cut_s=receipt['cut_s'],
        tle=receipt['causal_tle'],maximum_whole_run_seconds=480)),flush=True)
    if not launch:return
    result=pipeline.run(ATTEMPT/'training-input.json',ATTEMPT/'output',maximum_seconds=480,tle_root=TLE_ROOT)
    if result.get('provenance',{}).get('tle_sha256',snapshot.digest)!=snapshot.digest:
        raise ValueError('Public causal selection changed after preflight; do not accept replay')
    print(json.dumps(dict(stage='terminal',state=result['state'],reason=result.get('reason'),
        elapsed_seconds=result.get('elapsed_seconds'),selection=result.get('selection'),
        output=str(ATTEMPT/'output'))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true')
    args=parser.parse_args();run(launch=args.run)
