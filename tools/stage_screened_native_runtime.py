"""Stage the pinned integer-screened detector only after complete qualification."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from stage_native_glrt_runtime import (
    KIND,
    fractional_qualification,
    install,
    verify,
    verify_files,
)

PREFIX = 'src/leo/analysis/starlink/'
DATA = 'reports/2026_11_03_algo07_runtime_iteration021/receipts/'
DOMAIN = 'reports/2026_11_03_algo07_runtime_iteration022/'
SCREEN_BUILD = 'reports/2026_11_03_algo07_runtime_iteration020/receipts/native-build.json'
CASES = ['glrt-native-DS26-0046', 'glrt-native-DS27-0004', 'glrt-native-DS28-0002']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def screen_requirements(domain, sparse, stress):
    d, s, t = domain['summary'], sparse['summary'], stress['summary']
    if not (d['covered'] and d['cases'] == 135 and d['prefix_values_exact'] == 1_000_001
            and d['unsupported_rejected'] == 6 and 0 <= d['maximum_bound_fraction'] <= 1):
        raise ValueError('Integer domain challenge is incomplete')
    if not (s['all_bit_exact'] and s['cases'] == 54 and s['exact_values'] == 59670
            and s['native_rejections'] == 5):
        raise ValueError('Actual sparse native qualification is incomplete')
    if not (t['exact'] and t['cases'] == 117 and t['screened'] == 45
            and t['complete_fallback'] == 72 and t['screen_kind'] == 'integer_vnni'):
        raise ValueError('Integrated screen/fallback qualification is incomplete')


def validate_members(original, inventory, build):
    extensions = ['__init__.py', '_native_acquisition.c', '_native_acquisition_grid.inc',
                  '_native_acquisition.cpython-312-x86_64-linux-gnu.so']
    additions = {PREFIX+n for n in ['coarse_screen.py', '_screen_bounds.py', '_screen_exact.py',
                                    '_screen_selection.py', '_screen_integer.py']}
    additions |= {PREFIX+folder+'/'+n for folder in ('_screen_native', '_sparse_native')
                  for n in extensions}
    changes = [PREFIX+'acquisition.py']
    if (set(inventory)-set(original) != additions or set(original)-set(inventory)
            or {n for n in original if inventory[n] != original[n]} != set(changes)
            or set(build['additions']) != additions or build['changes'] != changes
            or build['screen_kind'] != 'integer_vnni'):
        raise ValueError('Unexpected screened runtime members or original-kernel changes')
    return additions, changes


def stage(repo, revision, base, candidate, *, execute=False):
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Exact committed revision required')
    repo, base, candidate = [p.resolve(strict=True) for p in (repo, base, candidate)]

    def committed(name):
        return subprocess.check_output(['git', '-C', str(repo), 'show', f'{revision}:{name}'])

    names = [DATA+n for n in ('detector-build.json', 'full-parity.json', 'downstream-parity.json',
                              'policy.json', 'sparse-build.json', 'sparse-stress.json',
                              'detector-stress.json')]
    names += [DATA+'deployed/'+case+suffix for case in CASES
              for suffix in ('.json', '-verification.json')]
    names += [DOMAIN+'receipts/domain-review.json', DOMAIN+'NUMERICAL_DOMAIN.md', SCREEN_BUILD]
    proofs = {n: committed(n) for n in names}

    def data(name):
        return json.loads(proofs[name])

    build = data(DATA+'detector-build.json')
    native = data(DATA+'full-parity.json')
    domain = data(DOMAIN+'receipts/domain-review.json')
    fractional_qualification(native, data(DATA+'downstream-parity.json'),
                             [data(DATA+'deployed/'+c+'.json') for c in CASES],
                             data(DATA+'policy.json'))
    screen_requirements(domain, data(DATA+'sparse-stress.json'), data(DATA+'detector-stress.json'))
    original = verify(base, build['base_pin'])['files_sha256']
    inventory = build['files_sha256']
    verify_files(candidate, inventory)
    additions, changes = validate_members(original, inventory, build)
    if (Path(build['base']).resolve() != base or Path(build['candidate']).resolve() != candidate
            or Path(native['candidate']['runtime']).resolve() != candidate):
        raise ValueError('Full qualification belongs to a different runtime')
    verify_files(Path(native['baseline']['runtime']),
                 {n: v for n, v in original.items()
                  if n.startswith('src/') and Path(n).suffix in ('.py', '.so')})
    for n in additions:
        if ('/_screen_native/' not in n and '/_sparse_native/' not in n
                and sha(committed(n)) != inventory[n]):
            raise ValueError('Committed component differs from tested runtime: '+n)
    for name, expected in domain['source_pins'].items():
        if sha(committed('tools/'+name)) != expected:
            raise ValueError('Domain review source differs: '+name)
    for case in CASES:
        receipt = data(DATA+'deployed/'+case+'-verification.json')
        if not (receipt['exit_code'] == 0 and receipt['source_bytes_verified']
                and receipt['fixture_before']['verified'] and receipt['fixture_after']['verified']
                and receipt['build_receipt_sha256'] == sha(proofs[DATA+'detector-build.json'])):
            raise ValueError('Paired detector qualification belongs to different bytes')
    for folder, proof, expected in [('_screen_native', SCREEN_BUILD,
                                     build['screen_receipt_sha256']),
                                    ('_sparse_native', DATA+'sparse-build.json',
                                     build['sparse_receipt_sha256'])]:
        compiled = data(proof)
        if (sha(proofs[proof]) != expected or compiled['base_pin'] != build['base_pin']
                or '-ffast-math' in compiled['compile_command']):
            raise ValueError('Native extension provenance differs')
        for n in additions:
            if (n.startswith(PREFIX+folder+'/') and not n.endswith('__init__.py')
                    and inventory[n] != compiled['files_sha256'][PREFIX+Path(n).name]):
                raise ValueError('Compiled extension member differs: '+n)
    if domain['build_sha256'] != sha(proofs[SCREEN_BUILD]):
        raise ValueError('Domain review covers a different integer screen')
    target = Path('/opt/leo-native-glrt-runtime')/revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, qualification='integer-screen-and-batched-exact-columns',
                revision=revision, release=str(target), base=str(base),
                tested_candidate=str(candidate),
                numerical_changes=changes, additions=sorted(additions),
                python='/opt/leo-fast-auto/20261010-r1/venv/bin/python',
                service_mutation=False, IQ_or_database_mutation=False,
                qualification_sha256={n: sha(v) for n, v in proofs.items()})
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError('Root stages immutable native runtimes')
    composition = dict(original_sha256=original, candidate_sha256=inventory)
    extras = {'prototype-build.json': (json.dumps(composition, indent=2)+'\n').encode(),
              'tools/stage_native_glrt_runtime.py': committed('tools/stage_native_glrt_runtime.py'),
              'tools/stage_screened_native_runtime.py':
                  committed('tools/stage_screened_native_runtime.py')}
    extras.update({'qualification/screened/'+str(i)+'-'+Path(n).name: v
                   for i, (n, v) in enumerate(proofs.items())})
    return install(plan, candidate, inventory, extras)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'base', 'candidate'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    result = stage(args.repo, args.revision, args.base, args.candidate, execute=args.execute)
    print(json.dumps(result))
