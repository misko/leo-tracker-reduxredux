"""Prepare named frozen blocks sequentially through bounded read-only exporters."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('blocks', nargs='+'); args = parser.parse_args()
    assert len(args.blocks) == len(set(args.blocks))
    selection = json.loads((HERE/'selection.json').read_text())
    members = {}
    for block in args.blocks:
        rows = [r for r in selection['captures'] if r['block_id'] == block]
        assert len(rows) == 4
        assert all(not (HERE/'prepared'/r['unit_id']).exists() for r in rows)
        assert not (HERE/'prepared'/('preparation-'+block)).exists()
        members[block] = rows
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               PYTHONPATH=str(HERE.parents[1]/'src'))
    for block, rows in members.items():
        print(json.dumps(dict(block=block, stage='preparing')), flush=True)
        subprocess.run([sys.executable, str(HERE/'prepare_block.py'), block], env=env, check=True)
        assert all((HERE/'prepared'/r['unit_id']/'observations.json').exists() for r in rows), 'input failure retained; stop queue'
        subprocess.run([sys.executable, str(HERE/'prepare_block_orbits.py'), block], env=env, check=True)
        assert all((HERE/'prepared'/r['unit_id']/'orbits-extended.json').exists() for r in rows), 'orbit failure retained; stop queue'
        print(json.dumps(dict(block=block, stage='admitted')), flush=True)


if __name__ == '__main__': main()
