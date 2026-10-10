"""Prepared154 one-slice entry; no automatic retry or evaluation."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from ports import HERE, ROOT, PRIOR, POLICY, load, continue_slice


def verify(plan):
    if plan['policy'] != POLICY:
        raise ValueError('runtime policy changed')
    if str(Path(sys.executable).absolute()) != plan['runtime']['interpreter']:
        raise ValueError('immutable interpreter path required')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('singlethread required')
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError('closure changed ' + name)
    for name, expected in plan['runtime']['sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('runtime changed ' + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('condition', choices=POLICY['conditions'])
    parser.add_argument('branch', choices=POLICY['discovery_policies'])
    parser.add_argument('--protocol', type=Path, default=HERE / 'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE / 'results')
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    verify(plan)  # Before inherited imports or public recording access.
    members = [m for m in plan['members'] if m['label'] == args.label]
    if len(members) != 1:
        raise ValueError('label outside cohort')
    previous = load('ports151_runtime154', PRIOR / 'ports.py')
    entry, driver, adapter = previous.dependencies()
    inference = load('inference151_runtime154', PRIOR / 'inference_binding.py')
    member = members[0]
    loader = inference.make_loader(entry, member)
    row = continue_slice(plan, member, args.branch, args.condition,
                         args.output / args.label / args.condition / args.branch,
                         loader, driver, adapter)
    print(args.label, args.condition, args.branch, row['status'], flush=True)


if __name__ == '__main__':
    main()
