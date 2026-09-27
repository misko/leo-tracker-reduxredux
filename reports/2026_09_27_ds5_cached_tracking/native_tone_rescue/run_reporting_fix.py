"""Pinned reporting-only adapter for the frozen tone-rescue experiment.

The original summary dereferences a None raw-rescue output in later stages.
Only its summary input is adapted; detector calls, rows and stage gates stay
unchanged. New receipts use distinct names and carry this adapter's lock.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_tone_rescue_evaluation as original

LOCK = HERE / 'reporting_fix_lock.json'
ORIGINAL_SUMMARIZE = original.summarize


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze():
    parent = json.loads(original.SOURCE_LOCK.read_text())
    files = dict(parent['files'])
    for path in (Path(__file__), HERE / 'test_tone_reporting_fix.py',
                 original.SOURCE_LOCK, HERE / 'results.controls.json',
                 HERE / 'diagnostic_reporting_failure.json'):
        files[str(path.resolve())] = digest(path)
    for name, expected in files.items():
        if digest(name) != expected:
            raise ValueError(f'changed source: {name}')
    with LOCK.open('x') as stream:
        json.dump({'schema': 'org.leo.research.tone-reporting-fix/v1',
                   'change': 'omit absent raw comparator from summary only',
                   'files': files}, stream, indent=2)
        stream.write('\n')


def summarize(stage, rows):
    summary_rows = [
        {key: value for key, value in row.items()
         if key != 'raw_rescue_result' or value is not None}
        for row in rows
    ]
    value = ORIGINAL_SUMMARIZE(stage, summary_rows)
    value['reporting_adapter'] = {
        'lock_path': str(LOCK), 'lock_sha256': digest(LOCK),
        'description': 'Reporting-only None comparator correction; original rows unchanged',
    }
    return value


def run(stage):
    lock_hash = digest(LOCK)
    lock = json.loads(LOCK.read_text())
    for name, expected in lock['files'].items():
        if digest(name) != expected:
            raise ValueError(f'changed reporting adapter dependency: {name}')
    original.summarize = summarize
    original.result_path = lambda selected: HERE / (
        'results.controls.json' if selected == 'controls'
        else f'results.reporting_fix.{selected}.json')
    original.execute_stage(stage)
    if digest(LOCK) != lock_hash or any(
        digest(name) != expected for name, expected in lock['files'].items()
    ):
        raise ValueError('reporting adapter source changed during execution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--freeze', action='store_true')
    actions.add_argument('--stage', choices=('diagnostic', 'real'))
    args = parser.parse_args()
    freeze() if args.freeze else run(args.stage)
