"""Bounded metadata-only exposure inventory; no RF, fitting or input export."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import signal
import time

HERE = Path(__file__).resolve().parent
PRIOR = Path('/srv/bulk/leo/research/ds25-20261024')
LEDGER = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
CUTOFF = 1792852694000000000


def read(path):
    return json.loads(path.read_bytes())


def binding(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('300s metadata cap')))
    signal.alarm(300)
    sample_path = PRIOR / 'sample.json'
    execution_path = PRIOR / 'execution.json'
    table_path = PRIOR / 'tables/positions.csv'
    sample = read(sample_path)['selected']
    execution = {r['case']: r for r in read(execution_path)['receipts']}
    # Read a previously published reporting table, retaining presence/status only.
    # Coordinates and error magnitudes do not enter this inventory or any choice.
    with table_path.open() as handle:
        previous = list(csv.DictReader(handle))
    evaluated = {r['case'] for r in previous if r['error_km'] not in ('', 'None', 'nan')}
    records = []
    for r in sorted(sample, key=lambda x: (x['captured_utc_ns'], x['dataset_label'])):
        case = r['dataset_label']
        records.append(dict(case=case, parent_case=r.get('parent_dataset_label'),
            recording_id=r['recording_id'], session_ids=r['session_ids'],
            mode=r['mode'], captured_utc_ns=r['captured_utc_ns'],
            relative_to_cutoff='before' if r['captured_utc_ns'] < CUTOFF else 'at_or_after',
            frozen_execution_status=execution[case]['status'],
            frozen_execution_reason=execution[case].get('reason'),
            prior_geographic_result_in_positions_table=case in evaluated,
            exposure_class='published_geographic_result' if case in evaluated else 'published_failure_or_unavailable_accounting',
            untouched_established=False))
    # Contract names are run identities, not source session identities. Read
    # only their trailing metadata; do not load GLRT arrays or IQ payloads.
    contracts = {}
    for path in sorted(Path('/srv/bulk/leo/fast-scan-tracking-inputs').glob('*.json')):
        with path.open('rb') as handle:
            handle.seek(max(0, path.stat().st_size - 2048))
            tail = handle.read().decode()
        sessions = re.findall(r'"session_id"\s*:\s*"([^"]+)"', tail)
        rates = re.findall(r'"sample_rate_hz"\s*:\s*(\d+)', tail)
        digests = re.findall(r'"raw_recording_authority_digest"\s*:\s*"([^"]+)"', tail)
        qualifiers = re.findall(r'"qualified"\s*:\s*(true|false)', tail)
        if sessions:
            contracts.setdefault(sessions[-1], []).append(dict(path=str(path),
                bytes=path.stat().st_size, trailing_metadata_sha256=hashlib.sha256(tail.encode()).hexdigest(),
                sample_rate_hz=int(rates[-1]) if rates else None,
                raw_recording_authority_digest=digests[-1] if digests else None,
                qualified=qualifiers[-1]=='true' if qualifiers else None,
                full_document_or_GLRT_arrays_validated=False))
    missing = []
    for r in read(LEDGER)['rows']:
        if r['eligible']:
            continue
        matched = [p for s in r['session_ids'] for p in contracts.get(s, [])]
        raw_paths = [Path('/srv/bulk/leo/fast-scan-inputs') / (s + '.json') for s in r['session_ids']]
        job_path = Path('/srv/bulk/leo/fast-scan-automatic') / (r['recording_id'] + '.json')
        job = read(job_path) if job_path.is_file() else {}
        missing.append(dict(case=r['case'], recording_id=r['recording_id'], session_ids=r['session_ids'],
            source_session_matched_contract_metadata=matched,
            source_input_manifests=[binding(p) for p in raw_paths if p.is_file()],
            automatic_job=binding(job_path) if job else None,
            automatic_state=job.get('state'), automatic_failure=job.get('failure'),
            automatic_standard_stages=job.get('standard_stages'),
            published_contract_metadata_found=bool(matched),
            metadata_qualified_and_raw_identity_matches=any(p['qualified'] and p['raw_recording_authority_digest']==r['raw_authority_digest'] for p in matched),
            full_current_readiness_validated=False,
            raw_manifest_is_not_tracking_readiness=True, untouched_established=False))
    # One direct metadata directory only. No recursive corpus enumeration.
    # Recording-name timestamps are a proxy, not a new acquisition authority.
    later = []
    direct_jobs = 0
    for p in sorted(Path('/srv/bulk/leo/fast-scan-automatic').glob('*.json')):
        direct_jobs += 1
        m = re.search(r'fast8-auto-(\d{8})-(\d{6})-', p.stem)
        if not m:
            continue
        stamp = int(datetime.strptime(''.join(m.groups()), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).timestamp()) * 10**9
        if stamp < CUTOFF:
            continue
        d = read(p)
        session = d.get('session_id')
        matched = contracts.get(session, [])
        later.append(dict(recording_id=d.get('recording_id', p.stem),
            recording_name_time_proxy_utc_ns=stamp, automatic_state=d.get('state'),
            session_id=session, source_session_matched_contract_metadata=matched,
            full_current_readiness_validated=False,
            automatic_standard_stages=d.get('standard_stages'),
            job_metadata=binding(p), acquisition_membership_validated=False,
            prior_geographic_exposure='not established by this bounded inventory',
            untouched_established=False))
    result = dict(schema='metadata-exposure-inventory/v1', cutoff_utc_ns=CUTOFF,
        cutoff_utc='2026-10-24T14:38:14Z', source_bindings=[binding(p) for p in (sample_path, execution_path, table_path, LEDGER, Path(__file__))],
        known_frozen_records=records, original_ten_unavailable_current_checks=missing,
        post_cutoff_direct_job_metadata=later, direct_job_files_considered=direct_jobs,
        known_frozen_population=len(records), prior_geographic_cases=len(evaluated),
        original_ten_with_contract_metadata=sum(r['published_contract_metadata_found'] for r in missing),
        original_ten_metadata_qualified_and_identity_matched=sum(r['metadata_qualified_and_raw_identity_matches'] for r in missing),
        post_cutoff_metadata_jobs=len(later),
        no_untouched_validation_block_established=True,
        limitations=['No full corpus crawl, GLRT/RF read, export, database outcome search or acquisition membership mint.',
            'Source session metadata is matched independently of contract filename; full contracts and GLRT arrays are not loaded or validated.',
            'Production position-stage completion can expose geography; its absence does not establish no prior exposure.',
            'A later job filename time is only a metadata time proxy, not a canonical capture/10MSps authority.',
            'No exhaustive prior-report or unpublished-session exposure search was attempted.'],
        elapsed_seconds=time.monotonic()-began, compute_cap_seconds=300,
        position_fits=0, IQ_or_RF_arrays_loaded=False)
    out = HERE / 'exposure_inventory02.json'
    with out.open('x') as handle:
        json.dump(result, handle, indent=2);handle.write('\n')
    print(json.dumps({k:result[k] for k in ('known_frozen_population','prior_geographic_cases','original_ten_with_contract_metadata','original_ten_metadata_qualified_and_identity_matched','post_cutoff_metadata_jobs','direct_job_files_considered','elapsed_seconds')}))


if __name__ == '__main__':
    main()
