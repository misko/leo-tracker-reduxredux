"""Metadata-only binding of sealed full-fit position hypotheses."""
import copy
import hashlib
import json
import math
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / '2026_10_10_position_error_iter161'
AUTHORITY_SHA = '8283a1926b5d2e500425a532949878e524a448b62e64efb5d164c55f50bf501b'
INTEGRITY_SHA = 'fb62033164a8cfbc10ff31562b5ad6b7b10ca6d3cfab5afc02d1eb771f9ae875'
HYPOTHESIS_DIGEST = 'sha256:1866fc7a2addec1f40ea49e1fdcebc3097662ed95cc922fead559fd6eba691b8'
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
POLICY = dict(members=12, hypotheses=['zero-c', 'fitted-c'],
    modes=['train0', 'train1'], arms=['zero-c', 'fitted-c'], maximum_fits=96,
    workers=2, threads=1, shards=2, retries=0, maximum_seconds=90,
    maximum_iterations=600, timing_half_width_s=20, fixed_position=True,
    slope_half_width_hz_s=60, local_radius_km=25,
    local_center='hypothesis-position', seed='original155-zero-c-position-replaced',
    stationarity_tolerance=.001, objective_tolerance=1e-6,
    preference_tolerance=1e-6, physical_metadata='original-full-observations',
    prior_scaling='unchanged', references_before_all_terminal=False)
SOURCE_FILES = ('freeze.py', 'run.py', 'fit_core.py', 'test_freeze.py',
                'test_run.py', 'test_fit_core.py', 'preference.py',
                'test_preference.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project(receipt, claim, label, arm):
    identity = dict(label=label, mode='full', arm=arm,
                    protocol_sha256=HYPOTHESIS_DIGEST)
    if any(receipt.get(k) != v or claim.get(k) != v for k, v in identity.items()):
        raise ValueError('foreign full hypothesis receipt/claim')
    if receipt.get('status') != 'qualified':
        raise ValueError('full hypothesis unavailable; member must not be omitted')
    if receipt.get('audit', {}).get('qualified') is not True:
        raise ValueError('full hypothesis lacks independent qualification')
    vector = receipt['solver']['vector']
    if not isinstance(vector, list) or len(vector) < 2:
        raise ValueError('missing hypothesis coordinates')
    position = vector[:2]
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in position):
        raise ValueError('invalid hypothesis coordinates')
    return list(position)


def prepare():
    """Verify published bytes and return a plan; no models or output writes."""
    authority, integrity_path = PRIOR/'protocol.json', PRIOR/'REPORT_INTEGRITY.json'
    if sha(authority) != AUTHORITY_SHA or sha(integrity_path) != INTEGRITY_SHA:
        raise ValueError('published161 authority changed')
    integrity = json.loads(integrity_path.read_text())
    if integrity.get('protocol.json') != AUTHORITY_SHA:
        raise ValueError('161 publication protocol differs')
    for name, expected in integrity.items():
        if sha(PRIOR/name) != expected:
            raise ValueError('161 publication changed: ' + name)
    previous = json.loads(authority.read_text())
    plan = {key: copy.deepcopy(previous[key]) for key in
            ('members', 'source_sha256', 'input_sha256', 'runtime')}
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT/name) != expected:
                raise ValueError('inherited161 artifact changed: ' + name)
    if plan['runtime']['interpreter'] != INTERPRETER:
        raise ValueError('immutable47e required')
    for name, expected in plan['runtime']['sha256'].items():
        if sha(name) != expected:
            raise ValueError('runtime changed: ' + name)
    labels = [m['label'] for m in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact twelve inherited members required')
    # Only raw hashes and protocol identity are consumed from the outcome summary.
    summary = json.loads((PRIOR/'SUMMARY.json').read_text())
    if summary['protocol_sha256'] != HYPOTHESIS_DIGEST:
        raise ValueError('foreign161 summary')
    hashes = summary['raw_sha256']
    expected_names = {label+'/'+name for label in labels for name in
        ('claim.json', 'result.json', *[mode+'--'+arm+suffix
        for mode in ('full', 'train0', 'train1') for arm in ('zero-c', 'fitted-c')
        for suffix in ('.json', '.claim.json')])}
    if set(hashes) != expected_names:
        raise ValueError('161 raw inventory differs')
    with tarfile.open(PRIOR/'raw-receipts.tar.gz', 'r:gz') as archive:
        entries = archive.getmembers()
        if len(entries) != len(expected_names) or {e.name for e in entries} != expected_names:
            raise ValueError('161 archive inventory differs')
        for entry in entries:
            if not entry.isfile() or hashlib.sha256(archive.extractfile(entry).read()).hexdigest() != hashes[entry.name]:
                raise ValueError('161 archive receipt differs: ' + entry.name)
    for member in plan['members']:
        member['hypotheses'] = {}
        for arm in POLICY['hypotheses']:
            paths = [PRIOR/'results'/member['label']/('full--'+arm+suffix)
                     for suffix in ('.json', '.claim.json')]
            for path in paths:
                key = str(path.relative_to(PRIOR/'results'))
                if sha(path) != hashes[key]:
                    raise ValueError('local full receipt differs: ' + key)
                plan['input_sha256'][str(path.relative_to(ROOT))] = hashes[key]
            receipt, claim = [json.loads(path.read_text()) for path in paths]
            member['hypotheses'][arm] = dict(position=project(receipt, claim, member['label'], arm),
                raw_path=str(paths[0].relative_to(ROOT)), raw_sha256=sha(paths[0]),
                claim_path=str(paths[1].relative_to(ROOT)), claim_sha256=sha(paths[1]),
                protocol_sha256=HYPOTHESIS_DIGEST)
    # Outcome publication is preparation provenance, not inference admission.
    provenance = {str(path.relative_to(ROOT)): sha(path) for path in
        (integrity_path, PRIOR/'SUMMARY.json', PRIOR/'raw-receipts.tar.gz')}
    plan['input_sha256'][str(authority.relative_to(ROOT))] = AUTHORITY_SHA
    for name in SOURCE_FILES:
        path = HERE/name
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))] = sha(HERE/'PLAN.md')
    plan.update(policy=copy.deepcopy(POLICY), hypothesis_protocol_digest=HYPOTHESIS_DIGEST,
        preparation_provenance_sha256=provenance,
        scope='Consumed conditional geometry comparison; no independent validation')
    return plan


if __name__ == '__main__':
    raise SystemExit('Preparation only; root review before freeze')
