"""Run explicitly named prepared blocks sequentially; preserve all outcomes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blocks', nargs='+')
    args = parser.parse_args()
    if len(args.blocks) != len(set(args.blocks)):
        raise ValueError('duplicate block')
    selection = json.loads((HERE/'selection.json').read_text())
    for block in args.blocks:
        captures = [r for r in selection['captures'] if r['block_id'] == block]
        assert len(captures) == 4
        assert not (HERE/'independent-v2'/block).exists(), 'never restart existing batch'
        for capture in captures:
            for name in ['observations.json', 'orbits-extended.json']:
                assert (HERE/'prepared'/capture['unit_id']/name).exists()
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               PYTHONPATH=str(HERE.parents[1]/'src'))
    for block in args.blocks:
        print(json.dumps(dict(block=block, stage='start')), flush=True)
        subprocess.run([sys.executable, str(HERE/'window_batch.py'), block], env=env, check=True)
        # The batch enforces the existing per-fit deadlines and exclusive fit lock.
        # Audit is separately bounded and its complete output remains on disk.
        log = HERE/'independent-v2'/block/'audit-console.log'
        with log.open('x') as stream:
            subprocess.run([sys.executable, str(HERE/'evaluate_pilot.py'), block],
                           env=env, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        evaluation = json.loads((log.parent/'evaluation.json').read_text())
        print(json.dumps(dict(block=block, stage='audited',
            rows=[{k:r[k] for k in ['unit','accepted','error_m','failures']}
                  for r in evaluation['rows']])), flush=True)


if __name__ == '__main__':
    main()
