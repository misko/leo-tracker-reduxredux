"""Stage a pinned ALGO03 runtime only from committed exact-replay qualification."""

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from algo03_runtime_prototype import HIERARCHICAL_BASE
from algo03_runtime_release import ENVIRONMENT, KIND, digest, verify
from stage_algo07_runtime import (
    CANDIDATE_KERNEL_SHA256,
    KERNEL,
    PREPARED_FILES,
    committed,
    prepared_qualification,
)

BASE_REVISION = 'e67f67484c4f54316b33dfd8e12f6e68d09d1e13'
BASE_MANIFEST_SHA256 = '629894a99b17082bc82d422e780c89d8acb143a4a7c6bdffe7c82be6f88018b4'
REPORT = 'reports/2026_11_03_algo07_runtime_iteration007'
QUALIFICATION = 'reports/2026_11_03_algo07_runtime_iteration008/qualification.json'


def qualified_sources(repo, revision, baseline):
    proofs = {}

    def read(name):
        raw = committed(repo, revision, name)
        proofs[name] = raw
        return json.loads(raw)

    implementation = read(REPORT+'/implementation.json')
    qualification = read(QUALIFICATION)
    policy = read(REPORT+'/receipts/saved-policy-parity.json')
    population = read(REPORT+'/receipts/population-parity.json')
    if not (qualification['passed'] and qualification['scientific_tolerance'] == 0
            and {r['case'] for r in qualification['algo03_cases']} == {'single', 'joint'}
            and {r['case'] for r in qualification['algo07_cases']} == {'single', 'two_family'}
            and policy['passed'] and policy['cases'] == 175
            and population['passed'] and len(population['results']) == 16
            and all(r['passed'] and r['input_tensors_and_output_values_exact']
                    for r in population['results'])):
        raise ValueError('Incomplete ALGO03 runtime qualification')
    for row in qualification['algo03_cases']+qualification['algo07_cases']:
        parity = read(row['parity_path'])
        if not (parity['passed'] and not parity['differences']
                and parity['exact_leaves'] > 0 and parity.get('differing_floats', 0) == 0):
            raise ValueError('Scientific parity failed: '+row['case'])
        if (row in qualification['algo03_cases']
                and not (parity.get('both_calibration_arms_required')
                         and parity.get('tolerance') == 0)):
            raise ValueError('Paired exact ALGO03 comparison required')
        for name in row['timing_paths']:
            timing = read(name)
            if not (timing['successful_execution'] and not timing['timed_out']
                    and timing['reference_after']['verified']):
                raise ValueError('Incomplete or mutated replay: '+name)
    files = implementation['files_sha256']
    if set(files) != set(HIERARCHICAL_BASE):
        raise ValueError('Unexpected hierarchical numerical overrides')
    overrides = {}
    for name, expected in files.items():
        if not (baseline['files_sha256'][name] == HIERARCHICAL_BASE[name]
                == implementation['baseline_files_sha256'][name]):
            raise ValueError('Hierarchical baseline differs: '+name)
        data = committed(repo, revision, name)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Hierarchical source differs from replay: '+name)
        overrides[name] = data
    return overrides, proofs


def snapshot_launcher(original):
    old = '''    for relative, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen ALGO03 member changed: " + relative)
'''
    after = '    audit = check_read_audit(output, child.pid)'
    if original.count(old) != 1 or original.count(after) != 1:
        raise ValueError('Unexpected frozen snapshot launcher')
    # The original scientific manifest hash is still checked immediately before
    # this block. The replacement binds every source byte of this composition.
    return original.replace(old, '    from algo03_runtime_release import verify\n'
                            '    verify(ROOT)\n').replace(after, '    verify(ROOT)\n'+after)


def stage(repo, revision, base, *, execute=False):
    repo, base = Path(repo).resolve(), Path(base).resolve()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Exact committed revision required')
    if digest(base/'release-manifest.json') != BASE_MANIFEST_SHA256:
        raise ValueError('Installed ALGO03 manifest changed')
    baseline = json.loads((base/'release-manifest.json').read_text())
    if baseline['revision'] != BASE_REVISION:
        raise ValueError('Unexpected installed baseline')
    for name, sha in baseline['files_sha256'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or digest(base/p) != sha:
            raise ValueError('Installed baseline member changed: '+name)
    overrides, proofs = prepared_qualification(repo, revision, baseline)
    hierarchical, extra = qualified_sources(repo, revision, baseline)
    overrides.update(hierarchical)
    proofs.update(extra)
    overrides[KERNEL] = committed(repo, revision, KERNEL)
    if hashlib.sha256(overrides[KERNEL]).hexdigest() != CANDIDATE_KERNEL_SHA256:
        raise ValueError('Unqualified phase-pair contraction kernel')
    overrides['tools/algo03_runtime_release.py'] = committed(
        repo, revision, 'tools/algo03_runtime_release.py')
    overrides['tools/run_algo03_snapshot.py'] = snapshot_launcher(
        (base/'tools/run_algo03_snapshot.py').read_text()).encode()
    target = Path('/opt/leo-fast-graph-runtime-algo03')/revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, revision=revision, release=str(target), base_release=str(base),
                base_manifest_sha256=BASE_MANIFEST_SHA256,
                numerical_overrides=[KERNEL, *PREPARED_FILES, *HIERARCHICAL_BASE],
                science_policy_changed=False, service_mutation=False,
                required_environment=ENVIRONMENT,
                qualification_sha256={k: hashlib.sha256(v).hexdigest() for k, v in proofs.items()})
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError('Root stages qualified runtime compositions')
    target.mkdir(parents=True)
    (target/'.incomplete').touch()
    for name in baseline['files_sha256']:
        p = target/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base/name, p)
    for name, data in overrides.items():
        p = target/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    for name, data in proofs.items():
        p = target/'runtime-qualification'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    shutil.copyfile(base/'release-manifest.json', target/'reference-release-manifest.json')
    (target/'venv').symlink_to(base/'venv', target_is_directory=True)
    files = {str(p.relative_to(target)): digest(p) for p in target.rglob('*')
             if p.is_file() and not p.is_symlink() and p.name != '.incomplete'}
    expected = dict(baseline['files_sha256'])
    expected.update({k: hashlib.sha256(v).hexdigest() for k, v in overrides.items()})
    if any(files.get(k) != v for k, v in expected.items()):
        raise ValueError('Staged bytes differ')
    (target/'runtime-manifest.json').write_text(json.dumps(dict(plan, files_sha256=files),
                                                         indent=2)+'\n')
    pin = digest(target/'runtime-manifest.json')
    verify(target, pin)
    for p in target.rglob('*'):
        if not p.is_symlink():
            p.chmod(0o755 if p.is_dir() else 0o644)
    (target/'.incomplete').unlink()
    return dict(plan, runtime_manifest_sha256=pin, files=len(files))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--base-release', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    print(json.dumps(stage(a.source, a.revision, a.base_release, execute=a.execute)))
