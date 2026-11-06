"""External Linux perf accounting with verified fork inheritance and exact native audit.

Requires privileged perf and mount/network namespaces. No production changes.
Counters include the isolated harness and supervisor, not just scientific fits.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

EVENTS = ('cpu_core/cycles/', 'cpu_core/instructions/', 'task-clock')
WORKLOAD = '''import os, resource, sys, time
def work():
    value = 0
    for i in range(5000000):
        value += i % 97
    assert value > 0
if sys.argv[1] == 'parent':
    work()
else:
    pid = os.fork()
    if pid == 0:
        work()
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert status == 0
print({'parent_cpu': time.process_time(),
       'child_cpu': sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2])})
'''


def parse_counters(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = {}
    for row in rows:
        event = row['event']
        if event not in EVENTS or event in result:
            raise ValueError('Unexpected or duplicate perf event')
        try:
            value = float(row['counter-value'])
            running = float(row['pcnt-running'])
        except (ValueError, TypeError) as error:
            raise ValueError('Unavailable perf counter') from error
        if not math.isfinite(value) or value <= 0 or not 99 <= running <= 100:
            raise ValueError('Invalid or multiplexed perf counter')
        expected_unit = 'msec' if event == 'task-clock' else ''
        if row['unit'] != expected_unit:
            raise ValueError('Unexpected perf unit')
        result[event] = value
    if set(result) != set(EVENTS):
        raise ValueError('Missing perf counter')
    result['cpu_seconds'] = result['task-clock']/1000
    result['cycles_per_instruction'] = result[EVENTS[0]]/result[EVENTS[1]]
    result['average_active_ghz'] = result[EVENTS[0]]/result['cpu_seconds']/1e9
    return result


def record(root, name, command, *, inherit=True, cpus='0'):
    output = root/f'{name}-counters.jsonl'
    # Pin perf before it creates counters; pinning only its child permits
    # startup on an efficiency core, where cpu_core events cannot run.
    perf = ['sudo', '-n', 'taskset', '-c', cpus, 'perf', 'stat',
            '--json-output', '-o', str(output),
            '-e', ','.join(EVENTS)]
    if not inherit:
        perf.append('--no-inherit')
    full = [*perf, '--', *command]
    (root/f'{name}-command.json').write_text(json.dumps(full, indent=2)+'\n')
    began = time.perf_counter()
    with (root/f'{name}.log').open('xb') as log:
        outcome = subprocess.run(full, stdout=log, stderr=subprocess.STDOUT, check=False)
    receipt = dict(returncode=outcome.returncode, elapsed_seconds=time.perf_counter()-began,
                   inherit=inherit, command=full)
    (root/f'{name}-execution.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if outcome.returncode:
        raise RuntimeError(f'{name} failed; inspect its saved log')
    receipt['counters'] = parse_counters(output)
    return receipt


def verify(root):
    records = {}
    for name, mode, inherit in (('parent', 'parent', True), ('child', 'child', True),
                                ('child-excluded', 'child', False)):
        records[name] = record(root, name, ['taskset', '-c', '0', sys.executable, '-B',
                                           '-c', WORKLOAD, mode], inherit=inherit)
    instructions = {k:r['counters'][EVENTS[1]] for k,r in records.items()}
    included_ratio = instructions['child']/instructions['parent']
    excluded_ratio = instructions['child']/instructions['child-excluded']
    valid = .9 < included_ratio < 1.1 and excluded_ratio > 5
    result = dict(records=records, included_ratio=included_ratio,
                  included_vs_excluded_ratio=excluded_ratio, verified=valid,
                  workload=WORKLOAD)
    (root/'inheritance.json').write_text(json.dumps(result, indent=2)+'\n')
    if not valid:
        raise ValueError('Fork inheritance accounting failed verification')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--request', type=Path)
    p.add_argument('--reference-timing', type=Path)
    p.add_argument('--verify-only', action='store_true')
    args = p.parse_args()
    if not args.verify_only and (not args.request or not args.reference_timing):
        p.error('--request and --reference-timing required for native profiling')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [Path(__file__), Path('tools/qualify_algo07v3_cli.sh'),
             Path('tools/compare_algo07v3_runs.py'), *Path('src').rglob('*.py')]
    if args.request:
        paths.extend([args.request, args.reference_timing])
    bindings = {str(q.resolve()):hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    (root/'plan.json').write_text(json.dumps(dict(bindings=bindings, production_modified=False,
                                                events=EVENTS), indent=2)+'\n')
    verify(root)
    if not args.verify_only:
        request = json.loads(args.request.read_bytes())
        bundle = Path(request['native_input']['path']).parent
        request_path = root/'request.json'
        request_path.write_text(json.dumps(dict(request, output_root=str(root/'publication')),
                                           indent=2)+'\n')
        work = root/'native'
        work.mkdir()
        before = dict(load=os.getloadavg(), pressure=Path('/proc/pressure/cpu').read_text())
        measured = record(root, 'native', ['taskset', '-c', '0,1,2', 'sh',
            'tools/qualify_algo07v3_cli.sh', str(bundle), str(work), sys.executable,
            str(request_path), 'run', '1200'], cpus='0,1,2')
        after = dict(load=os.getloadavg(), pressure=Path('/proc/pressure/cpu').read_text())
        compare = [sys.executable, '-B', 'tools/compare_algo07v3_runs.py',
                   '--baseline-request', str(args.request),
                   '--baseline-timing', str(args.reference_timing),
                   '--candidate-request', str(request_path),
                   '--candidate-timing', str(work/'attempt/supervisor.json'),
                   '--output', str(root/'comparison.json')]
        with (root/'comparison.log').open('xb') as log:
            subprocess.run(compare, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = dict(measured=measured, resources_before=before, resources_after=after,
                      scope='perf includes isolated harness, preflight, supervisor and descendants',
                      scientific_equality=True, speedup=None, production_modified=False)
        (root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result), flush=True)
    changed = [q for q,h in bindings.items() if hashlib.sha256(Path(q).read_bytes()).hexdigest()!=h]
    (root/'binding-check.json').write_text(json.dumps(dict(changed=changed), indent=2)+'\n')
    if changed:
        raise ValueError('Bound sources changed while measuring')


if __name__ == '__main__':
    main()
