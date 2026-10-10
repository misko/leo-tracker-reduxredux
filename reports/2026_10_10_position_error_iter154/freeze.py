"""Metadata-only154 protocol preparation. Never write or execute a freeze."""
import copy
import hashlib
import json
from pathlib import Path
from ports import HERE, ROOT, PRIOR, POLICY

AUTHORITY_SHA = '5058d5785a8c897a187473dd09351d15fde3af91b485a5711bd474c5f3c7f4c8'
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(canonical_digest):
    authority = PRIOR / 'protocol.json'
    if sha(authority) != AUTHORITY_SHA:
        raise ValueError('151 authority changed')
    previous = json.loads(authority.read_text())
    old_digest = canonical_digest(previous)
    plan = dict(members=copy.deepcopy(previous['members']), policy=copy.deepcopy(POLICY),
                discovery_digest=old_digest, source_sha256=copy.deepcopy(previous['source_sha256']),
                input_sha256=copy.deepcopy(previous['input_sha256']),
                evaluation_source_sha256=copy.deepcopy(previous['evaluation_source_sha256']),
                historical_control_sha256={},
                scope='Consumed sealed151 twelve; fresh matched continuations, not deployed B7 parity')
    plan['input_sha256'][str(authority.relative_to(ROOT))] = AUTHORITY_SHA
    for member in plan['members']:
        search = PRIOR / 'results' / member['label'] / 'search'
        member['sealed_search_path'] = str(search.relative_to(ROOT))
        for branch in POLICY['discovery_policies']:
            path = PRIOR / 'results' / member['label'] / branch / 'result.json'
            plan['historical_control_sha256'][str(path.relative_to(ROOT))] = sha(path)
        result = json.loads((search / 'result.json').read_text())
        if result['status'] != 'complete' or result['protocol_sha256'] != old_digest or result['label'] != member['label']:
            raise ValueError('unsealed discovery')
        selected = [search / 'result.json', search / 'case.json']
        for branch in POLICY['discovery_policies']:
            regions = result['searches'][branch]['regions']
            if len(regions) != 3:
                raise ValueError('retained region count changed')
            arm = 'fitted-c' if branch == 'native' else 'zero-c'
            for region in regions:
                point = [region['east_km'], region['north_km']]
                for key in (['bootstrap', point], ['point', *point, arm]):
                    path = search / 'points' / (canonical_digest(key)[7:] + '.json')
                    row = json.loads(path.read_text())
                    if row['protocol_sha256'] != old_digest or row['key'] != key or row['status'] != 'complete':
                        raise ValueError('invalid original point authority')
                    selected.append(path)
        for path in selected:
            plan['input_sha256'][str(path.relative_to(ROOT))] = sha(path)
    files = ('own_arm.py', 'adapter.py', 'ports.py', 'execute.py', 'batch.py',
             'freeze.py', 'report.py', 'test_own_arm.py', 'test_adapter.py',
             'test_ports.py', 'test_report.py')
    for path in (HERE / name for name in files):
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    for path in (HERE / 'README.md', HERE / 'PLAN.md'):
        plan['input_sha256'][str(path.relative_to(ROOT))] = sha(path)
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError('closure changed ' + name)
    venv = Path(INTERPRETER).parents[1]
    runtime_paths = [Path(INTERPRETER).resolve(), venv / 'pyvenv.cfg']
    site = venv / 'lib/python3.14/site-packages'
    for name in ('numpy', 'numpy.libs', 'scipy', 'scipy.libs', 'sgp4'):
        runtime_paths.extend(p for p in (site / name).rglob('*')
                             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    plan['runtime'] = dict(interpreter=INTERPRETER,
                           sha256={str(p): sha(p) for p in runtime_paths})
    return plan


if __name__ == '__main__':
    raise SystemExit('Preparation only: no numeric freeze or recording execution')
