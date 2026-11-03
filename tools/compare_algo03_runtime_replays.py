"""Exact scientific comparison of complete private ALGO03 worker replays."""

import argparse
import hashlib
import json
from pathlib import Path

ACCOUNTING = {'seconds', 'total_seconds', 'recovery_seconds',
              'whole_recovery_deadline_monotonic', 'root_process_id',
              'supervisor_process_id'}
HASH_MAPS = {'source_hashes', 'source_receipts', 'source_support_receipt'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_read_receipts(root, audit):
    receipts = [json.loads(p.read_text())
                for p in (root/'recovery/read_receipts').glob('*.json')]
    observed = {r['pid'] for r in receipts}
    expected = 1+sum(len(r['python_spawns']) for r in receipts)
    supervisor = audit['supervisor_process_id']
    roots = [r['pid'] for r in receipts if r['parent_pid'] == supervisor]
    if not (len(receipts) == len(observed) == expected == audit['expected']
            and roots == [audit['root_process_id']]
            and not any(r['denied_paths'] for r in receipts)
            and all(r['parent_pid'] in observed | {supervisor} for r in receipts)):
        raise ValueError('Process read receipts do not reproduce terminal audit')


def verify_runtime(root, pin):
    root = Path(root).resolve()
    path = root / ('runtime-manifest.json' if (root/'runtime-manifest.json').exists()
                   else 'release-manifest.json')
    if digest(path) != pin:
        raise ValueError('Runtime manifest differs from explicit pin')
    files = json.loads(path.read_text())['files_sha256']
    if not files:
        raise ValueError('Empty runtime inventory')
    for name, expected in files.items():
        member = root/name
        if (Path(name).is_absolute() or not member.resolve().is_relative_to(root)
                or digest(member) != expected):
            raise ValueError('Runtime member differs: '+name)
    return len(files)


def compare(left, right, left_runtime, right_runtime):
    roots = [Path(p).resolve() for p in (left, right)]
    runtimes = [Path(p).resolve() for p in (left_runtime, right_runtime)]
    differences, checked_receipts = [], []
    remaining_budget_differences = []
    exact_leaves = 0
    inventories = [{str(p.relative_to(root)): p for p in root.rglob('*.json')
                    if not any(k in p.relative_to(root).parts
                               for k in ('read_receipts', 'matplotlib-cache'))}
                   for root in roots]

    def normalized(value, side):
        return value.replace(str(roots[side]), '<WORKER>').replace(
            str(runtimes[side]), '<RUNTIME>')

    def hashed_sources(mapping, side):
        result = {}
        for name, expected in mapping.items():
            original = Path(name)
            p = (original if original.is_absolute() else runtimes[side]/original).resolve()
            if p.is_relative_to(runtimes[side]):
                manifest = runtimes[side]/'runtime-manifest.json'
                if not manifest.exists():
                    manifest = runtimes[side]/'release-manifest.json'
                relative = str(p.relative_to(runtimes[side]))
                bound = json.loads(manifest.read_text())['files_sha256'].get(relative)
                if bound != expected or digest(p) != expected:
                    raise ValueError('Changed runtime source receipt: '+name)
                result[normalized(name, side)] = '<verified runtime source>'
                checked_receipts.append(dict(side=side, runtime_path=relative, sha256=expected))
                continue
            if not p.is_relative_to(roots[side]) or digest(p) != expected:
                raise ValueError('Unbound or changed result receipt: '+name)
            # Every referenced scientific JSON is separately compared below.
            relative = str(p.relative_to(roots[side]))
            if relative not in inventories[side]:
                raise ValueError('Hashed result omitted from comparison: '+name)
            result[normalized(name, side)] = '<verified and compared>'
            checked_receipts.append(dict(side=side, path=relative, sha256=expected))
        return result

    def visit(a, b, path, key=None):
        nonlocal exact_leaves
        if key in ACCOUNTING:
            return
        if key in HASH_MAPS:
            a, b = hashed_sources(a, 0), hashed_sources(b, 1)
        if key == 'adapter_hashes':
            for side, mapping in enumerate((a, b)):
                for name, expected in mapping.items():
                    p = (runtimes[side]/name).resolve()
                    if not p.is_relative_to(runtimes[side]) or digest(p) != expected:
                        raise ValueError('Adapter receipt differs: '+name)
            # Runtime bytes are qualified separately by explicit manifests.
            a, b = sorted(a), sorted(b)
        if isinstance(a, dict) and isinstance(b, dict):
            if a.keys() != b.keys():
                differences.append(dict(path=path, reason='keys'))
                return
            for k in a:
                # Remaining deadlines are not iteration budgets. Only account
                # for stages hitting neither deadline, with matched CLI limits.
                if (k == 'budget_seconds' and a[k] != b[k]
                        and all(v.get('status') == 'complete' and v.get('returncode') == 0
                                and 0 <= v.get('seconds', -1) < v[k] <= 600 for v in (a, b))):
                    remaining_budget_differences.append(dict(
                        path=path+'/'+k, baseline=a[k], candidate=b[k]))
                    continue
                visit(a[k], b[k], path+'/'+k, k)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                differences.append(dict(path=path, reason='length'))
                return
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                visit(x, y, path+'/'+str(i))
        else:
            if type(a) is type(b) and a == b:
                exact_leaves += 1
                return
            if isinstance(a, str) and isinstance(b, str):
                a, b = normalized(a, 0), normalized(b, 1)
            if type(a) is type(b) and a == b:
                exact_leaves += 1
            else:
                differences.append(dict(path=path, baseline=a, candidate=b))

    for side, root in enumerate(roots):
        terminal = json.loads((root/'terminal.json').read_text())
        audit = terminal['read_audit']
        if not (terminal['state'] == 'complete' and terminal['failure'] is None
                and audit['verified'] and audit['all_launched_processes_accounted']
                and audit['receipts'] == audit['expected'] > 0 and not audit['denied_paths']):
            raise ValueError('Replay or read audit incomplete: '+str(root))
        verify_read_receipts(root, audit)
        if not any(n.endswith('/control.json') for n in inventories[side]):
            raise ValueError('Missing paired scientific trial')
        for name, path in inventories[side].items():
            if (name.endswith(('/control.json', '/new_family.json'))
                    and set(json.loads(path.read_text())['arms']) != {'c0', 'fitted_c'}):
                raise ValueError('Missing calibration arm')
    a, b = inventories
    if a.keys() != b.keys():
        differences.append(dict(reason='file_inventory', left_only=sorted(a.keys()-b.keys()),
                                right_only=sorted(b.keys()-a.keys())))
    for name in sorted(a.keys() & b.keys()):
        visit(json.loads(a[name].read_text()), json.loads(b[name].read_text()), name)
    return dict(passed=not differences, files=len(a), exact_leaves=exact_leaves,
                differences=differences, verified_source_receipts=checked_receipts,
                ignored_accounting_fields=sorted(ACCOUNTING), tolerance=0,
                both_calibration_arms_required=True,
                completed_stage_deadline_differences=remaining_budget_differences,
                excluded_file_classes=['read_receipts (process ancestry independently validated)',
                                       'matplotlib-cache (presentation only)'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'baseline-runtime', 'candidate-runtime', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('baseline-pin', 'candidate-pin'):
        parser.add_argument('--'+name, required=True)
    a = parser.parse_args()
    counts = [verify_runtime(a.baseline_runtime, a.baseline_pin),
              verify_runtime(a.candidate_runtime, a.candidate_pin)]
    limits = []
    for root in (a.baseline, a.candidate):
        command = json.loads((root.parent/'launch.json').read_text())['command']
        limits.append(float(command[command.index('--maximum-seconds')+1]))
    if not 0 < limits[0] == limits[1] <= 1200:
        raise ValueError('Matched whole-run budgets required')
    result = compare(a.baseline, a.candidate, a.baseline_runtime, a.candidate_runtime)
    result['maximum_seconds'] = limits[0]
    result['verified_runtime_files'] = counts
    result['baseline_runtime_manifest_sha256'] = a.baseline_pin
    result['candidate_runtime_manifest_sha256'] = a.candidate_pin
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('verified_source_receipts', 'differences')}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
