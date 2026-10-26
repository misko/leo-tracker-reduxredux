"""Bound the existing public-contract preparation; no new inference or RF."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RUN = ROOT / 'prepared'
PLAN = Path('/srv/bulk/leo/research/ds24-precision-block-transfer-r01/COORDINATOR_PLAN.md')
SAMPLE_SHA = 'c19af75560ff1ff962ec73064c49b68d10fe94bd990b37b09f73e588242e8ec5'
LABELS = tuple('LATER4-%04d' % i for i in range(1, 5))
PRIOR_SECONDS = 13.850415848195553


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def members(sample):
    rows = sample['selected']
    if tuple(r['dataset_label'] for r in rows) != LABELS:
        raise ValueError('exact original four labels/order required')
    if len({r['recording_id'] for r in rows}) != 4 or len({r['session_id'] for r in rows}) != 4:
        raise ValueError('duplicate original identity')
    for row in rows:
        if row['recording_format'] != 'short_window_iq_recording' or row['sample_rate_hz'] != 10_000_000:
            raise ValueError('original fast 10 MS/s contract required')
        authority = row['capture_time_authority']
        if row['captured_utc_ns'] != authority['anchor_utc_ns']:
            raise ValueError('acquisition midpoint changed')
        if authority['causal_cutoff_utc_ns'] != authority['first_sample_earliest_utc_ns']:
            raise ValueError('BEFORE-bound causal cutoff changed')
    return rows


def all_slots(labels, completed):
    """An interrupted process never removes an original member."""
    return [completed.get(label, dict(case=label, status='not_attempted',
                                    reason='supervisor unavailable before launch'))
            for label in labels]


def sources():
    # Imports only: no context(), preparation, archive enumeration or propagation.
    sys.path[:0] = [str(REPO / 'tools'), str(REPO / 'src')]
    import prepare_algo02_ds23
    import evaluate_ds23_phase_refreshed as graph
    import ds23_radio_noise
    import prepare_ds23_genuine_causal_prior
    import export_ds23_causal_history
    import learn_ds23_causal_phase_forecast
    import analyze_dsx01_fixed_site
    paths = {Path(m.__file__).resolve() for m in tuple(sys.modules.values())
             if getattr(m, '__file__', None) and str(Path(m.__file__).resolve()).startswith(str(REPO))
             and Path(m.__file__).is_file()}
    paths |= {Path(graph.CONFIG), PLAN, Path(__file__), HERE / 'manifest.py',
              HERE / 'test_manifest.py', HERE / 'test_preparation.py', HERE / 'summary.json',
              HERE / 'validation_result.json', HERE / 'panel_protocol.json',
              HERE / 'owned_test_receipt.json', HERE / 'owned_test_receipt01.json', RUN / 'sample.json'}
    paths |= set(HERE.glob('LATER4-*_validation.json'))
    return {str(p): sha(p) for p in sorted(paths)}


def freeze():
    began = time.monotonic()
    if sha(RUN / 'sample.json') != SAMPLE_SHA:
        raise ValueError('original sample bytes changed')
    rows = members(read(RUN / 'sample.json'))
    receipt = read(HERE / 'owned_test_receipt.json')
    if not receipt['all_passed']:
        raise ValueError('owned fixtures must pass')
    bindings = sources()
    preparation_seconds = receipt['seconds'] + read(HERE / 'owned_test_receipt01.json')['seconds'] + time.monotonic() - began
    protocol = dict(schema='later4-preparation-01', fixed_labels=list(LABELS),
        identities=[{k: r[k] for k in ('dataset_label', 'recording_id', 'session_id', 'captured_utc_ns')}
                    for r in rows], sample_sha256=SAMPLE_SHA, source_and_input_bindings=bindings,
        metadata_seconds=PRIOR_SECONDS, freeze_and_tests_seconds=preparation_seconds,
        cumulative_worker_cap_seconds=600., per_case_cap_seconds=140., workers=2,
        fixed_case_reservation_seconds=560., no_retries=True,
        public_helper=str(REPO / 'tools/prepare_algo02_ds23.py'),
        command_stage='all', no_IQ_payload_or_detector=True, no_position_or_GPS=True,
        causal_clock='original acquisition bracket midpoint; BEFORE bound cutoff',
        parent_preflight='/srv/bulk/leo/research/ds24-precision-block-transfer-r01/audit/preparation_preflight.json',
        coordinator_go='/srv/bulk/leo/research/ds24-precision-block-transfer-r01/preparation_go.json')
    if PRIOR_SECONDS + preparation_seconds + 560 > 600:
        raise ValueError('fixed per-case reservations exceed remaining original budget')
    path = HERE / 'preparation_protocol.json'
    if path.exists():
        raise ValueError('preparation protocol is immutable; preserve before revision')
    write(path, protocol)
    print(json.dumps(dict(protocol=str(path), protocol_sha256=sha(path),
                          metadata_seconds=PRIOR_SECONDS, preparation_seconds=preparation_seconds)))


def verify():
    protocol = read(HERE / 'preparation_protocol.json')
    for path, digest in protocol['source_and_input_bindings'].items():
        if sha(path) != digest:
            raise ValueError('frozen source/input changed: ' + path)
    if sha(RUN / 'sample.json') != SAMPLE_SHA:
        raise ValueError('sample bytes changed')
    members(read(RUN / 'sample.json'))
    digest = sha(HERE / 'preparation_protocol.json')
    audit = read(protocol['parent_preflight'])
    go = read(protocol['coordinator_go'])
    if not audit['all_passed'] or audit['protocol_sha256'] != digest:
        raise ValueError('matching independent preflight required')
    if not go['authorized'] or go['protocol_sha256'] != digest:
        raise ValueError('matching coordinator GO required')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError(name + '=1 required')
    if os.geteuid() != 0:
        raise ValueError('existing helper uses privileged public-contract/archive reads; root supervisor required')
    return protocol


def case_job(label, protocol):
    began = time.monotonic()
    command = [str(REPO / '.venv/bin/python'), protocol['public_helper'],
               '--run-dir', str(RUN), '--case', label, '--stage', 'all']
    stdout = RUN / (label + '_preparation.stdout')
    stderr = RUN / (label + '_preparation.stderr')
    record = dict(case=label, status='running', command=command, no_retry=True)
    try:
        if (RUN / label).exists():
            raise ValueError('case output already exists; no resume/retry')
        with stdout.open('w') as out, stderr.open('w') as err:
            proc = subprocess.Popen(command, cwd=REPO, stdout=out, stderr=err,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                    start_new_session=True)
            record['pid'] = proc.pid
            timeout = max(.001, protocol['per_case_cap_seconds'] - (time.monotonic() - began))
            try:
                record['returncode'] = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                record.update(status='timeout', charged_seconds=protocol['per_case_cap_seconds'])
        if record['status'] != 'timeout':
            path = RUN / label / 'preparation_receipt.json'
            if record['returncode'] == 0 and path.exists():
                prepared = read(path)
                record.update(status=prepared['status'], preparation_receipt_sha256=sha(path))
                for relative, digest in prepared['files_sha256'].items():
                    if sha(RUN / relative) != digest:
                        raise ValueError('prepared output hash mismatch: ' + relative)
                if prepared['status'] == 'prepared':
                    clock = read(RUN / label / 'prepared.json')['metadata']
                    row = next(r for r in read(RUN / 'sample.json')['selected'] if r['dataset_label'] == label)
                    authority = row['capture_time_authority']
                    for key in ('anchor_utc_ns', 'causal_cutoff_utc_ns'):
                        if clock[key] != authority[key]:
                            raise ValueError('actual public winner clock differs: ' + key)
            else:
                record.update(status='failed', reason='nonzero helper or missing preparation receipt')
    except Exception as error:
        record.update(status='failed', reason=type(error).__name__ + ': ' + str(error))
    record['output_bindings'] = {str(p): sha(p) for p in sorted((RUN / label).rglob('*')) if p.is_file()}
    record['log_bindings'] = {str(p): sha(p) for p in (stdout, stderr) if p.exists()}
    record['elapsed_seconds'] = time.monotonic() - began
    record['charged_seconds'] = max(record.get('charged_seconds', 0), record['elapsed_seconds'])
    write(RUN / (label + '_execution.json'), record)
    return record


def run():
    protocol = verify()
    result_path = RUN / 'preparation_execution.json'
    if result_path.exists():
        raise ValueError('no repeated preparation execution')
    began = time.monotonic()
    completed = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(case_job, label, protocol): label for label in LABELS}
        for future in concurrent.futures.as_completed(jobs):
            label = jobs[future]
            try:
                completed[label] = future.result()
            except Exception as error:
                completed[label] = dict(case=label, status='supervisor_failed', reason=str(error), charged_seconds=140.)
            print(json.dumps(dict(case=label, status=completed[label]['status'])), flush=True)
    rows = all_slots(LABELS, completed)
    seconds = protocol['metadata_seconds'] + protocol['freeze_and_tests_seconds'] + sum(r['charged_seconds'] for r in rows)
    result = dict(protocol_sha256=sha(HERE / 'preparation_protocol.json'), rows=rows,
                  terminal=True, all_four_slots_preserved=True, cumulative_worker_seconds=seconds,
                  wall_seconds=time.monotonic() - began, budget_pass=seconds <= 600,
                  no_IQ_payload_detector_position_or_GPS=True)
    write(result_path, result)
    bindings = {str(p): sha(p) for p in sorted(RUN.rglob('*')) if p.is_file() and p.name != 'preparation_RF_seal.json'}
    write(RUN / 'preparation_RF_seal.json', dict(protocol_sha256=result['protocol_sha256'],
          terminal=True, all_four_slots_preserved=True, files=bindings))
    print(json.dumps(dict(result=str(result_path), seal=str(RUN / 'preparation_RF_seal.json'),
                          cumulative_worker_seconds=seconds, budget_pass=seconds <= 600)), flush=True)


if __name__ == '__main__':
    {'freeze': freeze, 'run': run}[sys.argv[1]]()
