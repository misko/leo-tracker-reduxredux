"""Compose and time the two-epoch research kernel against its installed baseline."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from profile_algo07_glrt import PROFILE
from stage_native_glrt_runtime import digest, verify, verify_files

PREFIX = 'src/leo/analysis/starlink/'
MEMBERS = ['_native_acquisition_grid.inc',
           '_native_acquisition.cpython-312-x86_64-linux-gnu.so']


def replacements(base_inventory, probe_inventory, original_inventory):
    names = ['_native_acquisition.c', *MEMBERS]
    for name in names:
        if base_inventory[PREFIX+'_screen_native/'+name] != original_inventory[PREFIX+name]:
            raise ValueError('Probe does not derive from the installed screen')
    if {n for n in probe_inventory if probe_inventory[n] != original_inventory[n]} != {
            PREFIX+n for n in MEMBERS}:
        raise ValueError('Probe has unrelated changes')
    return {PREFIX+'_screen_native/'+n: PREFIX+n for n in MEMBERS}


def compose(installed, pin, probe, output):
    installed, probe, output = installed.resolve(), probe.resolve(), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private runtime required')
    base = verify(installed, pin)
    receipt_path = probe/'epoch-pair.json'
    receipt_pin = digest(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    origin = Path(receipt['source'])
    if digest(origin/'screen-probe.json') != receipt['source_receipt_sha256']:
        raise ValueError('Original integer screen changed')
    original = json.loads((origin/'screen-probe.json').read_text())
    verify_files(origin, original['files_sha256'])
    verify_files(probe, receipt['files_sha256'])
    changed = replacements(base['files_sha256'], receipt['files_sha256'],
                           original['files_sha256'])
    output.mkdir()
    for name in base['files_sha256']:
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(probe/changed[name] if name in changed else installed/name, target)
    inventory = {n: digest(output/n) for n in base['files_sha256']}
    verify(installed, pin)
    verify_files(probe, receipt['files_sha256'])
    if digest(receipt_path) != receipt_pin:
        raise ValueError('Probe receipt changed')
    result = dict(base=str(installed), base_pin=pin, probe=str(probe), probe_pin=receipt_pin,
                  files_sha256=inventory, changes=sorted(changed), production_modified=False)
    PROFILE.write_new(output/'epoch-pair-detector.json', result)
    return dict(output=str(output), changes=sorted(changed))


def run(candidate, fixture, output):
    candidate, fixture, output = candidate.resolve(), fixture.resolve(), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private measurement directory required')
    build_path = candidate/'epoch-pair-detector.json'
    build_pin = digest(build_path)
    build = json.loads(build_path.read_text())
    base = Path(build['base'])
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    before = PROFILE.verify(fixture/'frozen.json')
    if not before['verified']:
        raise ValueError('Fixture changed')
    script = Path(__file__).resolve().parents[1]/(
        'reports/2026_11_03_algo07_runtime_iteration005/paired_windows.py')
    script_pin = digest(script)
    output.mkdir()
    command = [sys.executable, '-B', str(script), '--fixture', str(fixture),
               '--base', str(base), '--candidate', str(candidate),
               '--output', str(output/'paired.json')]
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    with (output/'run.log').open('x') as log:
        completed = subprocess.run(['timeout', '180s', *command], stdout=log,
                                   stderr=subprocess.STDOUT, env=env, check=False)
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    after = PROFILE.verify(fixture/'frozen.json')
    if not after['verified'] or digest(build_path) != build_pin or digest(script) != script_pin:
        raise ValueError('Qualification inputs changed')
    result = dict(command=command, exit_code=completed.returncode, build_pin=build_pin,
                  script_pin=script_pin, fixture_before=before, fixture_after=after,
                  source_bytes_verified=True, timeout_seconds=180, production_modified=False)
    PROFILE.write_new(output/'verification.json', result)
    if completed.returncode:
        raise RuntimeError('Paired execution failed; inspect run.log')
    paired = json.loads((output/'paired.json').read_text())
    return dict(windows=len(paired['rows']), exact=paired['all_receiver_outputs_exact'],
                totals=paired['totals'],
                speedup=paired['totals']['baseline']/paired['totals']['candidate'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('compose')
    for name in ('installed', 'probe', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--pin', required=True)
    p = commands.add_parser('run')
    for name in ('candidate', 'fixture', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    args = vars(parser.parse_args())
    command = args.pop('command')
    print(json.dumps({'compose': compose, 'run': run}[command](**args)))
