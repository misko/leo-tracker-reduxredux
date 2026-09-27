"""Correct timing-helper wiring after a zero-call validation runner failure."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_validation as original

LOCK = HERE / 'timing_adapter_lock.json'
WRITE = original.write_new


def freeze():
    parent = original.verify()
    failure = json.loads((HERE / 'results.json').read_text())
    assert not failure['rows'] and "has no attribute 'timed'" in failure['error']
    files = dict(parent['files'])
    for path in (Path(__file__), HERE/'test_tone_timing_adapter.py', HERE/'source_lock.json',
                 HERE/'generated.json', HERE/'results.json'):
        files[str(path.resolve())] = original.digest(path)
    WRITE(LOCK, {'files': files, 'change': 'bind existing raw_runner.timed; preserve failed receipt'})


def run():
    lock = json.loads(LOCK.read_text())
    assert all(original.digest(n) == h for n,h in lock['files'].items())
    original.evaluation.timed = original.evaluation.raw_runner.timed
    def write(path, value):
        assert path == HERE/'results.json'
        value['timing_adapter_lock_sha256'] = original.digest(LOCK)
        WRITE(HERE/'results.timing_adapter.json', value)
    original.write_new = write
    original.run()
    assert all(original.digest(n) == h for n,h in lock['files'].items())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze','run'))
    freeze() if parser.parse_args().action == 'freeze' else run()
