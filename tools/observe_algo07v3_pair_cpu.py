"""Recover reaped-child CPU accounting from a live sequential LU supervisor."""

import argparse
import json
import os
import time
from pathlib import Path


def fields(raw):
    # comm can contain spaces/parentheses; remaining fields start at state (3).
    values = raw.rsplit(')', 1)[1].split()
    return dict(start_ticks=int(values[19]), child_user_ticks=int(values[13]),
                child_system_ticks=int(values[14]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    args = parser.parse_args()
    root, proc = args.root.resolve(), Path('/proc') / str(args.pid)
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    output = root / 'reaped-child-cpu.json'
    if output.exists():
        raise ValueError('Observer receipt exists')
    baseline = json.loads((root / 'baseline/supervisor.json').read_bytes())
    if baseline['returncode'] != 0 or (root / 'candidate/supervisor.json').exists():
        raise ValueError('Observe after baseline wait and before candidate wait')
    command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
    if 'tools/qualify_algo07v3_shared_lu.py' not in command or str(root) not in command:
        raise ValueError('Wrong supervisor command')
    before = (proc / 'stat').read_text()
    identity = fields(before)['start_ticks']
    receipt = dict(pid=args.pid, command=command, clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),
                   baseline_raw_stat=before, baseline_completed_pid=baseline['pid'],
                   initial_children=(proc / 'task' / str(args.pid) / 'children').read_text(),
                   scope='Supervisor reaped children, including their reaped descendants',
                   complete=False, observation_started_unix=time.time())
    if len(receipt['initial_children'].split()) != 1:
        raise ValueError('Expected exactly one live candidate child')
    deadline = time.monotonic() + 1250
    while time.monotonic() < deadline:
        try:
            raw = (proc / 'stat').read_text()
        except FileNotFoundError:
            break
        if fields(raw)['start_ticks'] != identity:
            raise ValueError('Supervisor PID reused')
        if (root / 'candidate/supervisor.json').exists():
            candidate = json.loads((root / 'candidate/supervisor.json').read_bytes())
            a, b = fields(before), fields(raw)
            first = a['child_user_ticks'] + a['child_system_ticks']
            total = b['child_user_ticks'] + b['child_system_ticks']
            receipt.update(complete=candidate['returncode'] == 0, terminal_raw_stat=raw,
                           candidate_completed_pid=candidate['pid'],
                           baseline_cpu_seconds=first / receipt['clock_ticks_per_second'],
                           candidate_cpu_seconds=(total - first)
                           / receipt['clock_ticks_per_second'])
            break
        time.sleep(.2)
    receipt['observation_ended_unix'] = time.time()
    with output.open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
