"""Private paired publication replay with a declared larger real grid budget.

Does not rerun inference or replace earlier publications. A pass qualifies only
this declared presentation budget, not the original 30-second production limit.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from compare_algo07_star_publication import run as compare
from verify_algo07_star import CONFIG, SIDES, execution, load

from leo.cli.algo07_profile import digest, verify, write_new


def budget_driver(plan, seconds):
    """Keep the original scorer, real clock, grid locations and both arms."""
    if not math.isfinite(seconds) or not 30 < seconds <= 300:
        raise ValueError('Research grid budget must be greater than 30 and at most 300 seconds')
    code = plan['driver_code']
    if hashlib.sha256(code.encode()).hexdigest() != plan['driver_sha256']:
        raise ValueError('Original publication driver hash differs')
    return ('import functools\nimport leo.analysis.position_grid as _grid\n'
            '_grid.sample_position_grid = functools.partial(\n'
            f'    _grid.sample_position_grid, maximum_seconds={float(seconds)!r})\n' + code)


def run(args):
    case = args.case.resolve(strict=True)
    config = load(case)
    receipts = {}
    for side in SIDES:
        receipt = getattr(args, side + '_execution', None) or execution(case, config, side)
        if (receipt is None
                or json.loads(Path(receipt).read_text())['state'] != 'scientific_complete'):
            raise ValueError('Complete independent scientific executions required')
        receipts[side] = dict(path=str(receipt), sha256=digest(Path(receipt)))
    original = json.loads(args.publication_plan.read_text())
    if digest(args.presentation_manifest) != original['manifest_sha256']:
        raise ValueError('Presentation manifest hash differs')
    if not verify(args.presentation_manifest)['verified']:
        raise ValueError('Presentation runtime changed')
    code = budget_driver(original, args.grid_seconds)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or not output.is_relative_to(case):
        raise ValueError('New publication directory must be inside the private case')
    for side in SIDES:
        if output.is_relative_to(Path(config[side]).resolve()):
            raise ValueError('Keep publication separate from scientific stores')
    output.mkdir(exist_ok=False)
    plan = dict(kind='algo07-star-larger-real-publication-budget',
                grid_seconds=args.grid_seconds, maximum_seconds_per_publication=600,
                order=list(SIDES), original_production_budget_qualified=False,
                inference_rerun=False, performance_comparison=False,
                parent_plan=str(args.publication_plan),
                parent_plan_sha256=digest(args.publication_plan),
                case_configuration_sha256=digest(case / CONFIG), executions=receipts,
                presentation_manifest=str(args.presentation_manifest),
                presentation_manifest_sha256=digest(args.presentation_manifest),
                runner_path=str(Path(__file__).resolve()), runner_sha256=digest(Path(__file__)),
                driver_code=code, driver_sha256=hashlib.sha256(code.encode()).hexdigest())
    write_new(output / 'plan.json', plan)
    renderer = Path(original['renderer'])
    environment = dict(PYTHONPATH=f'{renderer / "src"}:{renderer / "tools"}',
                       OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for side in SIDES:
        command = ['timeout', '--kill-after=15', '600', original['python'], '-B', '-c', code,
                   config[side], str(output / side), config['run_id']]
        write_new(output / f'{side}-command.json', dict(command=command, environment=environment))
        print(f'{case.name}: publishing {side}, real grid budget {args.grid_seconds}s', flush=True)
        began = time.monotonic()
        with (output / f'{side}.log').open('x') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                    env={**os.environ, **environment}, check=False)
        write_new(output / f'{side}-execution.json', dict(
            returncode=result.returncode, wall_seconds=time.monotonic() - began))
        if result.returncode:
            raise ValueError(f'{side} publication failed; evidence retained, no retry')
    after = verify(args.presentation_manifest)
    write_new(output / 'manifest-after.json', after)
    if (not after['verified'] or load(case) != config
            or digest(Path(__file__)) != plan['runner_sha256']):
        raise ValueError('Publication inputs or runner changed')
    with contextlib.redirect_stdout(io.StringIO()):
        result = compare(SimpleNamespace(
            reference=Path(config['reference']), candidate=Path(config['candidate']),
            reference_publication=output / 'reference', candidate_publication=output / 'candidate',
            run_id=config['run_id'], output=output / 'comparison.json'))
    summary = dict(publication_exact=result['publication_exact'],
                   png_equal=sum(result['png_bytes_equal'].values()),
                   shared_grid_points=result['shared_grid_points'],
                   grid_difference_count=len(result['grid_differences']),
                   science_difference_count=len(result['science_differences']),
                   path_difference_count=len(result['path_differences']),
                   grid_seconds=args.grid_seconds, original_production_budget_qualified=False,
                   ds26_equivalence_verified=False, speedup_established=False)
    write_new(output / 'summary.json', summary)
    print(json.dumps(summary), flush=True)
    return int(not result['publication_exact'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('case', 'output', 'publication-plan', 'presentation-manifest'):
        parser.add_argument('--' + name, type=Path, required=True)
    for side in SIDES:
        parser.add_argument('--' + side + '-execution', type=Path)
    parser.add_argument('--grid-seconds', type=float, required=True)
    raise SystemExit(run(parser.parse_args()))
