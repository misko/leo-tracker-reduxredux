"""Four fixed full-input validations, reusing the previous public-port check."""
import time
STARTED=time.monotonic()
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import traceback
from manifest import selected_four,clock_authority,assert_identity

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-phase-shape-validation-r01/readiness')
SELECTION=Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/validation/cohort_ledger.json')


def worker():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('30second metadata cap including3second inspection allowance')))
    signal.setitimer(signal.ITIMER_REAL,max(.001,27-(time.monotonic()-STARTED)))
    spec=importlib.util.spec_from_file_location('previous_public_panel_validator',OLD/'validate_panel.py')
    prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior);prior.HERE=HERE
    from leo.storage.fast_scan import FastScanStore
    store=FastScanStore('/srv/bulk/leo');members=selected_four(json.loads(SELECTION.read_text()))
    rows=[]
    for i,item in enumerate(members,1):
        began=time.monotonic();case=f'LATER4-{i:04d}'
        try:
            job=store.automatic_status(item['recording_id'])
            if job['state']!='complete'or job['session_id']!=item['session_id']or job['run_id']!=item['current_run_id']:
                raise ValueError('frozen public run/status/session changed; no replacement')
            path=store.tracking_input_path(job['run_id'])
            if str(path)!=item['contract_metadata'][0]['path']:raise ValueError('public tracking authority changed')
            frozen=dict(case=case,recording_id=item['recording_id'],session_id=item['session_id'],run_id=job['run_id'],
                contract=prior.binding(path),automatic_job_metadata_sha256=prior.sha256_digest(prior.canonical_json_bytes(job)))
            adapted=dict(research_case=case,recording_id=item['recording_id'],session_id=item['session_id'])
            row=prior.validate(adapted,frozen,store)
            assert_identity(item,row)
            document=prior.read(path);clock=clock_authority(document)
            if clock['causal_cutoff_utc_ns']<1792852694000000000:raise ValueError('actual acquisition precedes fixed old cutoff')
            row['manifest_creation_start_utc_ns']=row['sample_member']['captured_utc_ns']
            row['sample_member']['captured_utc_ns']=clock['anchor_utc_ns']
            row['sample_member']['capture_time_authority']=clock
            row['clock_authority']=clock
            row['canonical_acquisition_utc']=prior.when(clock['anchor_utc_ns'])
            row['site_authority']=dict(recorded_identifiers=row['station_deployment_metadata'],
                evaluation_site_established=False,configuration_and_radio_are_not_location_proof=True,
                scope='station/deployment/pose/mount/setup identifiers in capture configuration; no GPS or inferred positions read')
        except TimeoutError:
            rows.append(dict(case=case,recording_id=item['recording_id'],status='blocked',error='metadata deadline reached'))
            break
        except Exception as exc:
            row=dict(case=case,recording_id=item['recording_id'],status='blocked',error=repr(exc),traceback=traceback.format_exc())
        row['seconds']=time.monotonic()-began;rows.append(row)
    seen={r['case']for r in rows}
    rows.extend(dict(case=f'LATER4-{i:04d}',recording_id=x['recording_id'],status='not_attempted',error='metadata deadline reached')
        for i,x in enumerate(members,1)if f'LATER4-{i:04d}'not in seen)
    signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps(dict(rows=rows,numerical_seconds=time.monotonic()-STARTED+3.,initial_inspection_allowance_seconds=3.,
        IQ_payloads_read=False,detector_calls=0,position_fits=0,geographic_errors_read=False),indent=2),flush=True)


if __name__=='__main__':worker()
