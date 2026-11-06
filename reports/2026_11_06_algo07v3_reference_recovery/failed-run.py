"""Fresh original-ALGO07/current-v3 comparison; no production writes.

Both legs use CPUs 0–2 and one BLAS thread. The v3 leg runs first, followed by
the frozen original workers. Export and oracle reconstruction run only after
both timing intervals. No reference result enters the native v3 process.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from leo.storage.fast_scan import FastScanStore


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def execute(root, name, command, *, allowed=(0,)):
    print('Starting ' + name, flush=True)
    write(root / f'{name}-resources-start.json', dict(
        load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
    began = time.monotonic()
    with (root / f'{name}.log').open('xb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    write(root / f'{name}-execution.json', dict(
        returncode=result.returncode, outer_seconds=time.monotonic() - began, command=command))
    write(root / f'{name}-resources-end.json', dict(
        load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
    if result.returncode not in allowed:
        raise RuntimeError(f'{name} failed with {result.returncode}; inspect preserved evidence')
    print('Completed ' + name, flush=True)


def main(root):
    repo = Path.cwd().resolve()
    previous = Path('/srv/bulk/leo-dev/algo07v3-pair-20261105')
    fixture = Path('/srv/bulk/leo/research/algo07-star-20261104/iteration000')
    old = read(previous / 'attempt002/DS26-0002/verify-algo07-star.json')
    bindings_path = Path(__file__).resolve().with_name('historical-bindings.json')
    replacements = read(bindings_path)
    root.mkdir(exist_ok=False)
    preflight = [sys.executable, '-B', str(Path(__file__).with_name('preflight.py')),
                 '--bindings', str(bindings_path), '--output', str(root / 'preflight.json')]
    execute(root, 'preflight', preflight)
    case = root / 'DS26-0002'
    case.mkdir()
    config = {k: old[k] for k in ('schema_version', 'kind', 'run_id', 'python', 'runtimes',
                                  'manifest', 'archive_manifest', 'archive_view', 'pins')}
    source = FastScanStore(old['reference'])
    for side in ('reference', 'candidate'):
        config[side] = str(case / side)
        source.export_replay_inputs(config['run_id'], case / side)
    sources = sorted((repo / 'src').rglob('*.py')) + [
        repo / 'tools/run_algo07_star.py', repo / 'tools/run_algo07_star_reuse.py']
    sources.extend(Path(row['target']) for row in replacements
                   if Path(row['target']) not in sources)
    pins = {str(path): digest(path) for path in sources}
    for row in replacements:
        assert digest(row['source']) == row['sha256']
        assert row['target'] in pins
        pins[row['target']] = row['sha256']
    config.update(candidate_terminal_read_reuse=True, candidate_source_tree=str(repo / 'src'),
                  candidate_source_pins=pins)
    write(case / 'verify-algo07-star.json', config)

    request = read(Path('/srv/bulk/leo-dev/algo07v3-family-integration-20261105')
                   / 'candidate-request.json')
    request['output_root'] = str(root / 'v3-publication')
    write(root / 'v3-request.json', request)
    (root / 'v3-run').mkdir()
    python = [sys.executable, '-B']
    commands = {}
    commands['candidate'] = [
        '/usr/bin/time', '-v', '-o', str(root / 'candidate-process-time.txt'),
        'taskset', '-c', '0,1,2', 'sh', 'tools/qualify_algo07v3_cli.sh',
        str(Path(request['native_input']['path']).parent), str(root / 'v3-run'),
        sys.executable, str(root / 'v3-request.json'), 'run', '1200']
    commands['reference'] = [
        '/usr/bin/time', '-v', '-o', str(root / 'reference-process-time.txt'),
        'taskset', '-c', '0,1,2', *python,
        'reports/2026_11_05_algo07v3_pair/run_reference.py', '--bindings', str(bindings_path),
        '--case', str(case), '--publication-plan', str(previous / 'publication-plan.json'),
        '--presentation-manifest', str(fixture / 'presentation-frozen.json'),
        '--output', str(root / 'reference-timing')]
    evidence = root / 'reference-evidence'
    commands['export'] = [*python, 'tools/export_algo07_star_stages.py',
                          '--root', config['reference'], '--output', str(evidence)]
    runtime = '/opt/leo-fast-graph-runtime-algo03/f286f3e3029ec17479f4aa2b41312e4220258944'
    for name in ('signed', 'inventory'):
        commands[name + '-oracle'] = [
            *python, f'tools/algo07v3_{name}_oracle.py', '--runtime', runtime,
            '--source', str(evidence / 'ALGO02/worker/inference/SCAN'),
            '--output', str(root / f'{name}-oracle.json')]
    commands['inventory-oracle'] += ['--scan-identities', *request['scan_identities']]
    commands['context-oracle'] = [
        *python, 'tools/algo07v3_context_count_oracle.py', '--evidence', str(evidence),
        '--runtime', '/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef',
        '--output', str(root / 'context-oracle.json')]
    commands['comparison'] = [
        *python, 'tools/compare_algo07v3_published.py', '--request', str(root / 'v3-request.json'),
        '--reference', config['reference'],
        '--reference-publication', str(root / 'reference-timing/publication'),
        '--reference-evidence', str(evidence),
        '--reference-timing', str(root / 'reference-timing/summary.json'),
        '--candidate-timing', str(root / 'v3-run/attempt/supervisor.json'),
        '--signed-oracle', str(root / 'signed-oracle.json'),
        '--inventory-oracle', str(root / 'inventory-oracle.json'),
        '--context-count-oracle', str(root / 'context-oracle.json'),
        '--output', str(root / 'comparison.json')]
    paths = [Path(__file__).resolve(), Path(__file__).with_name('preflight.py'),
             bindings_path, root / 'preflight.json', previous / 'publication-plan.json',
             fixture / 'presentation-frozen.json', root / 'v3-request.json',
             case / 'verify-algo07-star.json',
             repo / 'reports/2026_11_05_algo07v3_pair/run_reference.py']
    paths.extend(Path(row['source']) for row in replacements)
    paths += [repo / 'tools' / name for name in (
        'qualify_algo07v3_cli.sh', 'benchmark_algo07_star_case.py', 'verify_algo07_star.py',
        'export_algo07_star_stages.py', 'algo07v3_signed_oracle.py',
        'algo07v3_inventory_oracle.py', 'algo07v3_context_count_oracle.py',
        'compare_algo07v3_published.py')]
    file_bindings = {str(path): digest(path) for path in paths}
    # Bind actual current sources separately from the reference's private view.
    file_bindings.update({str(path): digest(path) for path in sources})
    write(root / 'plan.json', dict(
        commands=commands, sequence=list(commands), bindings=file_bindings,
        cpus=[0, 1, 2], blas_threads=1, production_modified=False,
        reference_policy='ordinary-clock admission; six original 1200-second worker budgets',
        candidate_policy='validation-all-work; 1200-second outer bound',
        equality_required='All public values and 17 mapped scientific audits',
        broader_admission_equivalence=False, shared_host=True, qualified_speedup=None))
    for name, command in commands.items():
        execute(root, name, command, allowed=(2,) if name == 'comparison' else (0,))
    for name, sha in file_bindings.items():
        assert digest(name) == sha, name
    comparison = read(root / 'comparison.json')
    assert comparison['all_checked_values_exact'] and not comparison['errors']
    assert not comparison['missing_audit_mappings']
    assert len(comparison['mapped_policies']) == 17
    print('Complete: fresh original/current pair and all 17 scientific mappings exact', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root.resolve())
