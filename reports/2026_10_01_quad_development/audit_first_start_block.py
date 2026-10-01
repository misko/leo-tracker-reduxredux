"""Bounded numerical audits of seven saved first-start solutions in one block."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

import window_inputs  # Establish the frozen research import paths.
from regression_batch import execute, verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('block')
    args = parser.parse_args()
    selection = sealed(HERE/'selection.json')
    units = [u for u in selection['evaluation_units'] if u['block_id'] == args.block]
    if len(units) != 7:
        raise ValueError('Block must have seven frozen windows')
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = HERE/'first-start-replay-v1'/args.block
        directory.mkdir(parents=True, exist_ok=False)
        sources, inputs = {}, {str(HERE/'selection.json'): digest(HERE/'selection.json')}
        for unit in units:
            parent = HERE/'independent-v2'/args.block/(unit['unit_id']+'.json')
            receipt = sealed(parent)
            sources.update(receipt['source_sha256'])
            inputs.update(receipt['inputs'])
            inputs[str(parent)] = digest(parent)
            inputs[receipt['height']['grid_path']] = receipt['height']['grid_sha256']
        for name in ('audit_first_start_block.py', 'materialize_first_start.py', 'screen_seed_prefix.py',
                     'evaluate_variant.py', 'evaluate_pilot.py', 'FIRST_START_REPLAY_PLAN.md'):
            sources[str(HERE/name)] = digest(HERE/name)
        verify_sources(sources)
        verify_sources(inputs)
        save(directory/'plan.json', dict(units=units, source_sha256=sources, inputs=inputs,
            qualification='Saved first-fit replay; no inference timing or inherited acceptance.'))
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(ROOT/'src'))
        rows = []
        for unit in units:
            arm = directory/unit['unit_id']
            arm.mkdir()
            freeze = arm/'sources.json'
            save(freeze, dict(units=[unit], source_sha256=sources, inputs=inputs))
            output = arm/(unit['unit_id']+'.json')
            launch = execute([sys.executable, str(HERE/'materialize_first_start.py'), unit['unit_id'],
                              '--output', str(output)], arm, unit['unit_id'], timeout_s=30, env=env)
            launch.update(freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None,
                          timing_scope='Replay materialization only; not acquisition or fitting')
            save(output.with_suffix('.launch.json'), launch)
            audit_launch = execute([sys.executable, str(HERE/'evaluate_variant.py'), str(arm)],
                                   arm, 'audit', timeout_s=60*unit['size'], env=env)
            save(arm/'audit-launch.json', audit_launch)
            verify_sources(sources)
            verify_sources(inputs)
            evaluation = sealed(arm/'evaluation.json') if (arm/'evaluation.json').exists() else None
            rows.append(dict(unit=unit, evaluation=evaluation, audit_launch=audit_launch))
            print(json.dumps(dict(unit=unit['unit_id'], audit_returncode=audit_launch['returncode'],
                                 audit=evaluation['rows'][0] if evaluation else None)), flush=True)
        save(directory/'summary.json', dict(rows=rows, qualification='Saved first-start audit; runtime fields are replay/audit cost, not inference.'))


if __name__ == '__main__':
    main()
