"""Stage an ALGO07 runtime composition from verified installed and committed bytes."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from algo07_runtime_release import digest, verify

BASE_REVISION = '7cafccaced18e6b0fa9266bd18339d61f0f9c1f4'
BASE_MANIFEST_SHA256 = '91a850cb727b92f2dc8e65e956bf3c3eaabb7e923f175c6138a1463a14eada9b'
KERNEL = 'src/leo/analysis/research/joint_predictive_families.py'
REFERENCE_KERNEL_SHA256 = 'dbf7f397753cf91f764c75630e208bb2162a5ce9e2c69305537ce8ba53385065'
CANDIDATE_KERNEL_SHA256 = '29ddc9c0c0595d5008074f1b88440ea0f9971773b3949b8d7e6703e45f24f7ef'
REPORT = 'reports/2026_11_03_algo07_runtime_iteration002'


def committed(repo, revision, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{revision}:{path}'])


def stage(repo, revision, base, *, execute=False):
    repo, base = Path(repo).resolve(), Path(base).resolve()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Exact committed revision required')
    if digest(base/'release-manifest.json') != BASE_MANIFEST_SHA256:
        raise ValueError('Installed base release manifest changed')
    baseline = json.loads((base/'release-manifest.json').read_text())
    if (baseline['revision'] != BASE_REVISION
            or baseline['files_sha256'][KERNEL] != REFERENCE_KERNEL_SHA256):
        raise ValueError('Unexpected scientific base')
    overrides = {
        KERNEL: committed(repo, revision, KERNEL),
        'tools/algo07_production_worker.py': committed(
            repo, revision, 'tools/algo07_runtime_worker.py'),
        'tools/algo07_runtime_release.py': committed(
            repo, revision, 'tools/algo07_runtime_release.py'),
    }
    if hashlib.sha256(overrides[KERNEL]).hexdigest() != CANDIDATE_KERNEL_SHA256:
        raise ValueError('Kernel differs from the qualified numerical trial')
    proofs = {}
    for name in ['protocol.json', 'full-replay-parity.json', 'population-reconstruction.json',
                 'policy-parity.json']:
        data = committed(repo, revision, REPORT+'/'+name)
        proofs[name] = data
    checks = {name:json.loads(data) for name, data in proofs.items()}
    if not (checks['full-replay-parity.json']['passed']
            and checks['full-replay-parity.json']['differing_floats'] == 0
            and checks['population-reconstruction.json']['passed']
            and len(checks['population-reconstruction.json']['results']) == 16
            and checks['policy-parity.json']['passed']
            and checks['policy-parity.json']['cases'] == 175):
        raise ValueError('Numerical qualification is incomplete')
    target = Path('/opt/leo-fast-graph-runtime-numerics')/revision
    if target.exists():
        raise FileExistsError(target)
    # Validate the complete installed base before constructing a new composition.
    for name, sha in baseline['files_sha256'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or digest(base/p) != sha:
            raise ValueError('Installed base member changed: '+name)
    plan = dict(kind='algo07-qualified-runtime-composition-v1', revision=revision,
                release=str(target), base_release=str(base), base_revision=BASE_REVISION,
                base_manifest_sha256=BASE_MANIFEST_SHA256,
                numerical_override=KERNEL, science_policy_changed=False,
                dependency_runtime=str(base/'venv'), service_mutation=False,
                qualification_sha256={k:hashlib.sha256(v).hexdigest() for k,v in proofs.items()},
                required_environment='LEO_ALGO07_RUNTIME_MANIFEST_SHA256')
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError('Root stages immutable runtime compositions')
    target.mkdir(parents=True)
    (target/'.incomplete').touch()
    for name in baseline['files_sha256']:
        p = target/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base/name, p)
    original = target/'tools/algo07_production_worker.py'
    shutil.copyfile(original, target/'tools/algo07_frozen_production_worker.py')
    for name, data in overrides.items():
        (target/name).write_bytes(data)
    for name, data in proofs.items():
        p = target/'runtime-qualification'/name
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(data)
    shutil.copyfile(base/'release-manifest.json', target/'reference-release-manifest.json')
    # Reuse the exact tested locked Python/dependency installation, read-only.
    (target/'venv').symlink_to(base/'venv', target_is_directory=True)
    files = {str(p.relative_to(target)):digest(p) for p in target.rglob('*')
             if p.is_file() and not p.is_symlink() and p.name != '.incomplete'}
    expected = dict(baseline['files_sha256'])
    expected['tools/algo07_frozen_production_worker.py'] = expected[
        'tools/algo07_production_worker.py']
    expected.update({k:hashlib.sha256(v).hexdigest() for k,v in overrides.items()})
    for name, sha in expected.items():
        if files.get(name) != sha:
            raise ValueError('Staged composition differs: '+name)
    manifest = dict(plan, files_sha256=files)
    (target/'runtime-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    checksum = digest(target/'runtime-manifest.json')
    verify(target, checksum)
    for p in target.rglob('*'):
        if not p.is_symlink():
            p.chmod(0o755 if p.is_dir() else 0o644)
    (target/'.incomplete').unlink()
    return dict(plan, runtime_manifest_sha256=checksum, files=len(files))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--base-release', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    print(json.dumps(stage(a.source, a.revision, a.base_release, execute=a.execute)))
