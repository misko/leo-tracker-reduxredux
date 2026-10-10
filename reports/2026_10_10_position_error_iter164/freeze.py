"""Metadata-only full-cohort successor; never reconstructs recording models."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
SOURCE_FILES = ('freeze.py', 'ports.py', 'execute.py', 'batch.py', 'inference_binding.py',
                'test_freeze.py', 'test_runtime.py', 'test_inference_binding.py',
                'test_numeric_ports.py')
AUTHORITIES = {
    '2026_10_09_position_error_iter107/protocol.json': '24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227',
    '2026_10_10_position_error_iter137/parity-bindings.json': '30d709f43fdd4db874aaf6e4f36b3474fc840add70a4c29e1db34b64fa979b4c',
    '2026_10_10_position_error_iter151/protocol.json': '5058d5785a8c897a187473dd09351d15fde3af91b485a5711bd474c5f3c7f4c8',
    '2026_10_10_position_error_iter163/protocol.json': '92f4da99a1580733fdfc31ef55800ccb4bb6c10f6cf21abaa8afafd14292f3ca',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execution_batches(members):
    """Balanced fixed metadata order, independent of results or binding success."""
    groups = {key: [] for key in ('DS16', 'DS17', 'DS18', 'newer')}
    for member in members:
        key = member['dataset'] if member['dataset'] in groups else 'newer'
        groups[key].append(member['label'])
    if [len(groups[k]) for k in groups] != [63, 51, 34, 45]:
        raise ValueError('full193 dataset membership required')
    queues = [sorted(v) for v in groups.values()]
    order = [q[i] for i in range(max(map(len, queues))) for q in queues if i < len(q)]
    if len(set(order)) != 193:
        raise ValueError('duplicate cohort label')
    return [order[:4]] + [order[i:i+16] for i in range(4, len(order), 16)]


def prepare():
    from ports import POLICY
    from inference_binding import prepare_bindings

    provenance = {}
    for name, expected in AUTHORITIES.items():
        path = HERE.parent/name
        if sha(path) != expected:
            raise ValueError('published authority changed: '+name)
        provenance[str(path.relative_to(ROOT))] = expected
    previous = json.loads((HERE.parent/'2026_10_10_position_error_iter151/protocol.json').read_text())
    runtime = json.loads((HERE.parent/'2026_10_10_position_error_iter163/protocol.json').read_text())['runtime']
    if runtime['interpreter'] != INTERPRETER:
        raise ValueError('immutable47e runtime required')
    plan = {k: copy.deepcopy(previous[k]) for k in ('source_sha256', 'evaluation_source_sha256', 'handoff_policy')}
    if POLICY != previous['policy']:
        raise ValueError('151 numerical policy changed')
    plan.update(members=prepare_bindings(), policy=copy.deepcopy(POLICY), runtime=copy.deepcopy(runtime),
                preparation_provenance_sha256=provenance, input_sha256={},
                scope='Full193 consumed single-pass discovery comparison; not deployed multiseparation B7 parity',
                reference_scope='Evaluation-only after all193 member selections and failures seal',
                resource_checkpoint='First4 then batches16; resource-only review, no accuracy-dependent membership or stopping')
    plan['execution_batches'] = execution_batches(plan['members'])
    for member in plan['members']:
        binding = member.get('binding')
        if binding:
            path = ROOT/binding['document_path']
            plan['input_sha256'][binding['document_path']] = binding['document_sha256']
            plan['source_sha256'][binding['loader_source']] = binding['loader_sha256']
    for name in SOURCE_FILES:
        path = HERE/name
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    for name in ('PLAN.md', 'REVIEW.md', 'INVENTORY_PLAN.md'):
        path = HERE/name
        plan['input_sha256'][str(path.relative_to(ROOT))] = sha(path)
    for group in ('source_sha256', 'evaluation_source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT/name) != expected:
                raise ValueError('preserved artifact changed: '+name)
    for name, expected in runtime['sha256'].items():
        if sha(name) != expected:
            raise ValueError('runtime changed: '+name)
    return plan


if __name__ == '__main__':
    raise SystemExit('Preparation only; root review before freeze')
