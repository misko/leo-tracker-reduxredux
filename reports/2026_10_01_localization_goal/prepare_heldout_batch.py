"""Bounded read-only DS12 track exports through the pinned public input reader."""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = '/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'
EXPORTER = ROOT/'tools/ds7_export_baseline.py'
EXPORTER_DIGEST = 'sha256:4d2e4bb96e687ca9fe1a035c138c87e55d2976d0136bffac182b1bc380c42dc4'


def verify_reader():
    expected = json.loads((HERE/'held-out/reader-provenance.json').read_text())['module_sha256']
    code = ('import importlib,hashlib,json; from pathlib import Path; '
            'names='+repr(list(expected))+'; '
            "print(json.dumps({n:'sha256:'+hashlib.sha256("
            'Path(importlib.import_module(n).__file__).read_bytes()).hexdigest() for n in names}))')
    call = subprocess.run(['sudo', '-n', '-u', 'leo', RUNTIME, '-c', code],
                          capture_output=True, text=True, check=True, timeout=30)
    actual = json.loads(call.stdout)
    if actual != expected:
        raise ValueError('deployed public reader source changed')
    if digest(EXPORTER) != EXPORTER_DIGEST:
        raise ValueError('exporter source changed')
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=int, required=True)
    parser.add_argument('--last', type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.first <= args.last <= 16 or args.last-args.first >= 8:
        raise ValueError('select one to eight frozen units')
    selection_path = HERE/'ds12-heldout-selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    selected = selection['units'][args.first-1:args.last]
    for unit in selected:
        if (HERE/'held-out'/unit['unit_id']).exists():
            raise FileExistsError('existing prepared unit '+unit['unit_id'])
    batch = HERE/'held-out'/f'preparation-{args.first:02d}-{args.last:02d}'
    batch.mkdir(exist_ok=False)
    before = verify_reader()
    evidence_path = ROOT/'reports/2026_09_30_gaussian_sum_single_scan/evidence.py'
    spec = importlib.util.spec_from_file_location('heldout_observation_adapter', evidence_path)
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    captures = {r['session_id']: r for r in selection['captures']}

    def run(unit):
        start = time.monotonic()
        name = unit['unit_id']
        temporary = Path('/tmp/leo-localization-goal-'+name.lower()+'-observations.json')
        if temporary.exists():
            raise FileExistsError(temporary)
        command = ['sudo', '-n', '-u', 'leo', 'env', 'OPENBLAS_NUM_THREADS=1',
                   'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
                   'timeout', '--kill-after=2s', '85s', RUNTIME, str(EXPORTER),
                   '--plan', str(selection_path), '--session', unit['session_id'],
                   '--output', str(temporary)]
        launch = execute(command, batch, name, timeout_s=90.)
        with (batch/(name+'.launch.json')).open('x') as stream:
            json.dump(launch, stream, indent=2)
        if launch['returncode'] != 0 or launch['timed_out']:
            return dict(unit=name, status='export_failed', launch=launch)
        raw = json.loads(temporary.read_text())
        assert raw['session_id'] == unit['session_id']
        assert raw['manifest_sha256'] == unit['manifest_sha256']
        target_dir = HERE/'held-out'/name
        # Validate before creating the unit directory or admitting artifacts.
        adapter.load_observation_export(temporary, captures[unit['session_id']])
        target_dir.mkdir(exist_ok=False)
        target = target_dir/'observations.json'
        with target.open('xb') as stream:
            stream.write(temporary.read_bytes())
        evidence = adapter.load_observation_export(target, captures[unit['session_id']])
        with (target_dir/'evidence.json').open('x') as stream:
            json.dump(evidence, stream, indent=2, allow_nan=False)
        receipt = dict(unit=name, session_id=unit['session_id'],
                       source_export_sha256=digest(target), exporter_sha256=digest(EXPORTER),
                       evidence_adapter_sha256=digest(evidence_path), runtime=RUNTIME,
                       tracks=len(raw['tracks']), elapsed_export_seconds=raw['elapsed_seconds'],
                       supervised_export_seconds=launch['elapsed_seconds'],
                       causal_snapshot_digest=raw['snapshot_sha256'],
                       raw_iq_read=False, new_rf_collected=False,
                       qualification='Observation preparation only; '
                       'orbit and reference admission pending')
        with (target_dir/'export-receipt.json').open('x') as stream:
            json.dump(receipt, stream, indent=2)
        result = dict(unit=name, status='prepared', tracks=len(raw['tracks']),
                      seconds=time.monotonic()-start, observation_sha256=digest(target))
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, selected))
    after = verify_reader()
    document = dict(source_sha256=digest(__file__), selection_sha256=digest(selection_path),
                    reader_before=before, reader_after=after, results=results)
    with (batch/'batch.json').open('x') as stream:
        json.dump(document, stream, indent=2)


if __name__ == '__main__':
    main()
