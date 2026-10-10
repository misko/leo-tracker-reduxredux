"""Metadata-only161 binding over published160 and its sealed fold inventory."""
import copy
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / '2026_10_10_position_error_iter160'
AUTHORITY_SHA = '2d9ca1ef32fdc3635517ffd8605b57ff1c164269bce49ab4a0b59fab2282bbac'
INTEGRITY_SHA = '991d9a68578e6d278fd6596b14e73c111f33438ecf75ac667fae322475fe4302'
FOLD_DIGEST = 'sha256:9b1ef64e0d8052560ab17eed30cd12e5c47602a244b250a5f2cff12a5e3cfbdb'
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
POLICY = dict(members=12, modes=['full','train0','train1'], arms=['zero-c','fitted-c'],
              maximum_fits=72, workers=2, threads=1, shards=2, retries=0,
              maximum_seconds=90, maximum_iterations=600, timing_half_width_s=20,
              fixed_position=False, slope_half_width_hz_s=60, local_radius_km=25,
              local_center='common-zero-endpoint', seed='original155-zero-c',
              stationarity_tolerance=.001, objective_tolerance=1e-6,
              physical_metadata='original-full-observations',
              prior_scaling='unchanged', references_before_all_terminal=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    """Return a verified plan without writing a protocol or importing models."""
    authority = PRIOR / 'protocol.json'
    integrity_path = PRIOR / 'REPORT_INTEGRITY.json'
    if sha(authority) != AUTHORITY_SHA or sha(integrity_path) != INTEGRITY_SHA:
        raise ValueError('published160 authority changed')
    integrity = json.loads(integrity_path.read_text())
    if integrity.get('protocol.json') != AUTHORITY_SHA:
        raise ValueError('160 publication protocol differs')
    # Verify publication bytes without parsing narrative or position outcomes.
    for name, expected in integrity.items():
        if sha(PRIOR / name) != expected:
            raise ValueError('160 publication changed: ' + name)
    previous = json.loads(authority.read_text())
    plan = {key:copy.deepcopy(previous[key]) for key in
            ('members','source_sha256','input_sha256','runtime')}
    for group in ('source_sha256','input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError('inherited160 artifact changed: ' + name)
    if plan['runtime']['interpreter'] != INTERPRETER:
        raise ValueError('immutable47e runtime required')
    for name, expected in plan['runtime']['sha256'].items():
        if sha(name) != expected:
            raise ValueError('inherited runtime changed: ' + name)
    summary = json.loads((PRIOR / 'SUMMARY.json').read_text())
    if summary['protocol_sha256'] != FOLD_DIGEST:
        raise ValueError('foreign160 fold summary')
    labels = [member['label'] for member in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact twelve inherited members required')
    expected_names = {label + suffix for label in labels for suffix in ('.json','.claim.json')}
    if set(summary['raw_sha256']) != expected_names:
        raise ValueError('160 raw inventory differs')
    with tarfile.open(PRIOR / 'raw-receipts.tar.gz', 'r:gz') as archive:
        entries = archive.getmembers()
        if len(entries) != 24 or {entry.name for entry in entries} != expected_names:
            raise ValueError('160 archive inventory differs')
        for entry in entries:
            if not entry.isfile():
                raise ValueError('160 archive requires ordinary receipt files')
            data = archive.extractfile(entry).read()
            if hashlib.sha256(data).hexdigest() != summary['raw_sha256'][entry.name]:
                raise ValueError('160 archived receipt differs: ' + entry.name)
    for member in plan['members']:
        for suffix in ('.json','.claim.json'):
            name = member['label'] + suffix
            path = PRIOR / 'results' / name
            expected = summary['raw_sha256'][name]
            if sha(path) != expected:
                raise ValueError('160 local receipt differs: ' + name)
            receipt = json.loads(path.read_text())
            if receipt.get('label') != member['label'] or receipt.get('protocol_sha256') != FOLD_DIGEST:
                raise ValueError('foreign160 fold receipt/claim')
            plan['input_sha256'][str(path.relative_to(ROOT))] = expected
        member.update(fold_path=str((PRIOR/'results'/(member['label']+'.json')).relative_to(ROOT)),
                      fold_sha256=summary['raw_sha256'][member['label']+'.json'],
                      fold_protocol_digest=FOLD_DIGEST)
    for path in (authority, integrity_path, PRIOR/'SUMMARY.json', PRIOR/'raw-receipts.tar.gz'):
        plan['input_sha256'][str(path.relative_to(ROOT))] = sha(path)
    for name in ('freeze.py','run.py','fit_core.py','test_fit_core.py', 'test_run.py', 'test_freeze.py'):
        path = HERE / name
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    path = HERE.parent / '2026_10_10_position_error_iter159/rows.py'
    plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))] = sha(HERE/'PLAN.md')
    plan.update(policy=copy.deepcopy(POLICY), fold_protocol_digest=FOLD_DIGEST,
                preparation_provenance_sha256={str(integrity_path.relative_to(ROOT)):INTEGRITY_SHA},
                scope='Consumed conditional grouped-training diagnostic; fresh full controls; no independent-validation claim')
    return plan


if __name__ == '__main__':
    raise SystemExit('Preparation only; root review before freeze or numerical execution')
