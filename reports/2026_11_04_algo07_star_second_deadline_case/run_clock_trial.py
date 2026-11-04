"""One real, guarded ALGO03 cancellation trial; run with its installed interpreter."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from algo03_shadow_worker import read, write
from run_algo03_shadow import check_read_audit
from run_algo03_snapshot import copy_snapshot

study, side = Path(sys.argv[1]).resolve(strict=True), sys.argv[2]
plan = read(study / 'plan.json')
assert side in plan['order'] and Path(sys.executable).resolve() == Path(plan['python']).resolve()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def verify():
    assert digest(plan['manifest']) == plan['manifest_sha256']
    rows = read(plan['manifest'])['files']
    for row in rows:
        assert digest(row['path']) == row['sha256'], row['path']
    for path, expected in plan['source_pins'].items():
        assert digest(path) == expected, path
    return dict(verified=True, files=len(rows), source_files=len(plan['source_pins']))


before = verify()
entry = plan['inputs'][side]
assert digest(entry['descriptor']) == entry['descriptor_sha256']
output = study / side
output.mkdir(exist_ok=False)
copy_snapshot(entry['descriptor'], output / 'snapshot')
source_names = {'algo03_stage_clock_fixture.py', 'algo03_clock_worker.py'}
for path in plan['source_pins']:
    if Path(path).name in source_names:
        shutil.copyfile(path, output / Path(path).name)
control = {k: plan[k] for k in ('maximum_seconds', 'schedule', 'stop_after')}
write(output / 'clock-control.json', control)
runtime = Path(plan['runtime'])
environment = dict(os.environ, **plan['environment'], PYTHONDONTWRITEBYTECODE='1',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   PYTHONPATH=os.pathsep.join(map(str, (runtime / 'deploy/fast_graph_guard',
                                                       runtime / 'src', runtime / 'tools'))),
                   LEO_FAST_GRAPH_RUN_ROOT=str(output),
                   LEO_FAST_GRAPH_INPUT=str(output / 'snapshot/inference/SCAN/tracking.json'),
                   LEO_FAST_GRAPH_SOURCE_ROOT=str(runtime),
                   LEO_FAST_GRAPH_TLE_ROOT=str(output / 'unused-tle-archive'),
                   MPLCONFIGDIR=str(output / 'matplotlib-cache'))
command = [plan['python'], '-B', str(output / 'algo03_clock_worker.py'), str(output)]
write(study / f'{side}-launch.json', dict(command=command, real_wall_limit_seconds=1200,
                                        plan_sha256=digest(study / 'plan.json'), before=before))
began = time.monotonic()
with (output / 'worker.log').open('xb') as log:
    child = subprocess.Popen(command, cwd=runtime, env=environment,
                             stdout=log, stderr=subprocess.STDOUT)
    try:
        code = child.wait(timeout=plan['real_wall_limit_seconds'])
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            code = child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            code = child.wait()
audit = check_read_audit(output, child.pid)
result = dict(returncode=code, real_wall_seconds=time.monotonic() - began,
              read_audit=audit, after=verify(), production_deadline_behavior_qualified=False,
              numerical_children_stubbed=False)
write(study / f'{side}-execution.json', result)
print(json.dumps(result), flush=True)
if code != 0 or not audit['verified']:
    raise SystemExit(1)
