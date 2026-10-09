"""Hash-bound lean readers; never fit, write checkpoints, or invent aliases."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ADAPTER=ROOT/'reports/2026_10_08_hard60_bounded_recovery/inputs.py'


def read_sanitized(source):
    path=HERE/source['sanitized_path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sanitized_sha256']
    return json.loads(path.read_text())


def original_point(member,basin):
    """Exact original semantic key; model compatibility is a caller precondition."""
    if not basin.startswith('point:') or basin.count(':')!=2:raise ValueError('Expected ordinary point key')
    binding=member.get('original_checkpoint_binding')
    if binding is None:return None
    store=RegionalCheckpointStore(Path(member['raw_input_root']),member['member']['session_id'],binding)
    return store.get(member['original_configuration_signature']+':'+basin)


def failure_point(member,failure):
    """Read exactly a recorded, hash-verified104 bootstrap source through get."""
    attempts=[a for a in failure['attempts'] if a.get('contains_bootstrap')]
    if not attempts:return None
    record=attempts[0]
    if record['port'].startswith('RegionalCheckpointStore.get'):
        value=original_point(member,failure['basin'])
    elif record['port']=='ExperimentCheckpoints.get':
        spec=importlib.util.spec_from_file_location('frozen107checkpoint_adapter',ADAPTER)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        baseline=next(s for s in member['sources'] if s['name']=='baseline')
        source_path=baseline['source'].get('path')
        if source_path:
            document=json.loads((ROOT/source_path).read_text())
        else:
            from leo.storage.regional_position_v2 import Hard60Store
            document=Hard60Store(Path(member['raw_input_root'])).status(member['member']['session_id']).manifest.document.model_dump(mode='json')
        regional=next(s for s in member['sources'] if s['source'].get('path')==failure['source'])
        config=read_sanitized(regional)['configuration']['run']
        store=module.ExperimentCheckpoints(ROOT/record['directory'],dict(baseline=canonical_digest(document),config=config))
        value=store.get(record['key'])
    else:raise ValueError('Unsupported frozen port')
    assert value is not None and canonical_digest(value)==record['value_sha256']
    assert value.get('result') and 'bootstrap' in value['result'] and 'fits' in value['result']
    return value
