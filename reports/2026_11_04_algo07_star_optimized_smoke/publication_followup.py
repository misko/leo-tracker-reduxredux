"""Execute one pinned, independent publication pair; retain every first result."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from compare_algo07_star_publication import run as compare

from leo.cli.algo07_profile import digest, verify, write_new

case = Path(sys.argv[1]).resolve(strict=True)
base = Path('/srv/bulk/leo/research/algo07-star-20261104/iteration000')
config = json.loads((case / 'verify-algo07-star.json').read_text())
for side in ('reference', 'candidate'):
    receipts = sorted(case.glob(f'verify-run-{side}-*/execution.json'))
    assert receipts and json.loads(receipts[-1].read_text())['state'] == 'scientific_complete'
manifest = base / 'presentation-frozen.json'
assert verify(manifest)['verified']
original = base / 'DS26-0002/controlled-publication-001/plan.json'
plan = json.loads(original.read_text())
code = plan['driver_code']
assert hashlib.sha256(code.encode()).hexdigest() == plan['driver_sha256']
assert digest(manifest) == plan['manifest_sha256']
out = case / 'publication-001'
out.mkdir(exist_ok=False)
plan.update(kind='algo07-star-first-pinned-publication-pair', order=['reference', 'candidate'],
            scope='First ordinary wall-clock publication comparison for this pair',
            parent_plan=str(original), parent_plan_sha256=digest(original),
            runner_path=str(Path(__file__).resolve()), runner_sha256=digest(Path(__file__)),
            case_configuration_sha256=digest(case / 'verify-algo07-star.json'),
            maximum_seconds_per_publication=600, performance_comparison=False)
write_new(out / 'plan.json', plan)
renderer = Path(plan['renderer'])
env = dict(PYTHONPATH=f'{renderer / "src"}:{renderer / "tools"}',
           OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
for side in plan['order']:
    command = ['timeout', '--kill-after=15', '600', plan['python'], '-B', '-c', code,
               config[side], str(out / side), config['run_id']]
    write_new(out / f'{side}-command.json', dict(command=command, environment=env))
    print(f'{case.name}: publishing {side}', flush=True)
    start = time.monotonic()
    with (out / f'{side}.log').open('x') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, **env}, check=False)
    write_new(out / f'{side}-execution.json',
              dict(returncode=result.returncode, wall_seconds=time.monotonic() - start))
    if result.returncode:
        raise SystemExit(f'{side} publication failed: {result.returncode}; evidence retained')
    line = (out / f'{side}.log').read_text().splitlines()[-1]
    row = json.loads(line)
    print(json.dumps({k: v for k, v in row.items() if k != 'source_terminal'}), flush=True)
after = verify(manifest)
write_new(out / 'manifest-after.json', after)
assert after['verified']
with contextlib.redirect_stdout(io.StringIO()):
    comparison = compare(SimpleNamespace(
        reference=Path(config['reference']), candidate=Path(config['candidate']),
        reference_publication=out / 'reference', candidate_publication=out / 'candidate',
        run_id=config['run_id'], output=out / 'comparison.json'))
print(json.dumps(dict(publication_exact=comparison['publication_exact'],
                      png_equal=sum(comparison['png_bytes_equal'].values()),
                      shared_grid_points=comparison['shared_grid_points'],
                      shared_grid_difference_count=len(comparison['shared_grid_differences']),
                      science_difference_count=len(comparison['science_differences']),
                      grid_differences=comparison['grid_differences'])), flush=True)
