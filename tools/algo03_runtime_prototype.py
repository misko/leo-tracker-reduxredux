"""Build a research-only ALGO03 composition from explicitly bound runtime changes."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from stage_algo07_runtime import KERNEL, PREPARED_FILES, PREPARED_REPORT

BASE = Path('/opt/leo-fast-graph/e67f67484c4f54316b33dfd8e12f6e68d09d1e13')
SCIENCE = 'reports/ALGO03/releases/2026-10-30-r1/manifest.json'
HIERARCHICAL_BASE = {
    'tools/dsx01_hierarchical_bound.py':
        '2042ab17ac0920488683241c96dc9a05a6d006592ba0ab30a819876dc8c74d58',
    'tools/dsx01_joint_marginal.py':
        'cf12f2d60bcdff60dffd5eed6872503ec71df905cc6f7363c71e3d386721df0f',
    'tools/probe_ds23_history_calibrated_phase.py':
        'a394f0b671cc6bed0a073cd8826e242f1db2e9265c073a69f8f0a9b95b6e6e9f',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(repo, output, *, hierarchical=False, geometry_cache_sha256=None,
          original_contractions=False):
    output = output.resolve()
    if not output.is_relative_to('/srv/bulk/leo/research') or output.exists():
        raise ValueError('A new private research directory is required')
    base_manifest = json.loads((BASE/'release-manifest.json').read_text())
    implementation = json.loads((repo/PREPARED_REPORT/'implementation.json').read_text())
    allowed = [*(() if original_contractions else (KERNEL,)), *PREPARED_FILES]
    for name, expected in base_manifest['files_sha256'].items():
        if digest(BASE/name) != expected:
            raise ValueError('Installed base differs: '+name)
    for name in PREPARED_FILES:
        if implementation['baseline_files_sha256'][name] != base_manifest['files_sha256'].get(name):
            raise ValueError('ALGO03 and qualified ALGO07 bases differ: '+name)
        expected = implementation['files_sha256'][name]
        if geometry_cache_sha256 and name == 'tools/predictive_new_family.py':
            expected = geometry_cache_sha256
        if digest(repo/name) != expected:
            raise ValueError('Qualified implementation differs: '+name)
    if digest(repo/KERNEL) != '29ddc9c0c0595d5008074f1b88440ea0f9971773b3949b8d7e6703e45f24f7ef':
        raise ValueError('Unexpected contraction kernel')
    if hierarchical:
        for name, expected in HIERARCHICAL_BASE.items():
            if base_manifest['files_sha256'][name] != expected:
                raise ValueError('Unexpected hierarchical baseline: '+name)
        allowed.extend(HIERARCHICAL_BASE)
    output.mkdir(parents=True, exist_ok=False)
    for name in base_manifest['files_sha256']:
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE/name, target)
    shutil.copyfile(BASE/'release-manifest.json', output/'reference-release-manifest.json')
    for name in allowed:
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo/name, target)
    shutil.copyfile(repo/'tools/algo03_runtime_prototype_verify.py',
                    output/'tools/algo03_runtime_prototype_verify.py')
    path = output/'tools/run_algo03_snapshot.py'
    text = path.read_text()
    old = '''    for relative, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen ALGO03 member changed: " + relative)
'''
    if text.count(old) != 1:
        raise ValueError('Unexpected original ALGO03 verification block')
    text = text.replace(old, '''    from algo03_runtime_prototype_verify import verify
    verify(ROOT)
''')
    # The original scientific manifest remains byte-identical and is still checked.
    # The complete explicit runtime composition replaces only its member-byte check.
    text = text.replace('    audit = check_read_audit(output, child.pid)',
                        '    verify(ROOT)\n    audit = check_read_audit(output, child.pid)')
    path.write_text(text)
    os.symlink(BASE/'venv', output/'venv')
    files = {str(p.relative_to(output)): digest(p) for p in output.rglob('*')
             if p.is_file() and not p.is_symlink()}
    manifest = dict(kind='algo03-runtime-research-prototype-v1', files_sha256=files,
                    original_release=str(BASE),
                    original_manifest_sha256=digest(BASE/'release-manifest.json'),
                    qualified_algo07_files=[*(() if original_contractions else (KERNEL,)),
                                           *(n for n in PREPARED_FILES
                                             if not (geometry_cache_sha256
                                                     and n == 'tools/predictive_new_family.py'))],
                    experimental_files=(list(HIERARCHICAL_BASE) if hierarchical else [])
                        + (['tools/predictive_new_family.py'] if geometry_cache_sha256 else []),
                    geometry_cache_sha256=geometry_cache_sha256,
                    original_contractions=original_contractions,
                    production_modified=False,
                    algo03_science_qualified=False, policy_changed=False)
    (output/'runtime-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return dict(root=str(output), manifest_sha256=digest(output/'runtime-manifest.json'),
                files=len(files), production_modified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--hierarchical', action='store_true')
    p.add_argument('--geometry-cache-sha256', help='Explicit pin for an unqualified cache fix')
    p.add_argument('--original-contractions', action='store_true',
                   help='Retain original ALGO03 contraction bytes for an exact-order ablation')
    a = p.parse_args()
    print(json.dumps(build(a.repo.resolve(), a.output, hierarchical=a.hierarchical,
                          geometry_cache_sha256=a.geometry_cache_sha256,
                          original_contractions=a.original_contractions)))
