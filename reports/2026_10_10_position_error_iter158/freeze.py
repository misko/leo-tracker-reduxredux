"""Strict metadata-only inheritance; no model, outcome or reference loading."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent/'2026_10_10_position_error_iter155/protocol.json'
AUTHORITY_SHA = 'c713a3a4c33a422feedf73915aea1e3e236c7ed1daa6a85064ac0c5d7b79f292'
PRIOR_DIGEST = 'sha256:309505e70b6f00763ac0a3303eeba07d9b2f25118d9282b7890567cb49a8ef50'
POLICY = dict(members=12, arms=['zero-c','fitted-c'], source_condition='control',
              discovery_policy='native', maximum_scalar_calls_per_receiver=512,
              maximum_anchor_calls_per_endpoint=1, maximum_orbit_calls_per_endpoint=1,
              maximum_joint_calls_per_endpoint=1025, maximum_seconds_per_endpoint=30,
              receiver_log_width=5e-5, combined_log_width=1e-4,
              workers=2, threads=1, shards=2, members_per_shard=6,
              objective_tolerance=1e-6, stationarity_tolerance=.001,
              retries=0, optimizer=False, references=False,
              full_support=True, nearest_image_maximum_sigma_hz=1000)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    if sha(PRIOR) != AUTHORITY_SHA:
        raise ValueError('immutable155 protocol changed')
    previous = json.loads(PRIOR.read_text())
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in previous[group].items():
            if sha(ROOT/name) != expected:
                raise ValueError('inherited numerical/input closure changed: '+name)
    for name, expected in previous['runtime']['sha256'].items():
        if sha(name) != expected:
            raise ValueError('inherited runtime changed: '+name)
    plan = {key:copy.deepcopy(previous[key]) for key in
            ('members','source_sha256','input_sha256','runtime')}
    plan['policy'] = copy.deepcopy(POLICY)
    plan['scope'] = 'Consumed fixed-endpoint conditional integration; no position outcome or fit'
    plan['preparation_provenance_sha256'] = {str(PRIOR.relative_to(ROOT)):AUTHORITY_SHA}
    # Bind prior successful callback evidence, preserving all twelve pairs.
    for member in plan['members']:
        path = PRIOR.parent/'results'/(member['label']+'.json')
        receipt = json.loads(path.read_text())
        if (receipt['label'] != member['label'] or receipt['status'] != 'complete'
                or receipt.get('protocol_sha256') != PRIOR_DIGEST
                or receipt['matched_model'] is not True
                or set(receipt['arms']) != {'fitted-c','zero-c'}
                or any(a['status'] != 'passed' for a in receipt['arms'].values())):
            raise ValueError('prior parity evidence incomplete: '+member['label'])
        plan['input_sha256'][str(path.relative_to(ROOT))] = sha(path)
    sources = [HERE/name for name in ('endpoint.py','run.py','freeze.py','test_endpoint.py','test_run.py')]
    sources += [HERE.parent/'2026_10_10_position_error_iter156'/'envelopes.py',
                HERE.parent/'2026_10_10_position_error_iter157'/'adaptive.py']
    for path in sources:
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))] = sha(HERE/'PLAN.md')
    return plan


if __name__ == '__main__':
    raise SystemExit('Source review and tests precede an explicit protocol write')
