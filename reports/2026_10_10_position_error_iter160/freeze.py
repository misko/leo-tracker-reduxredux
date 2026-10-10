"""Metadata-only successor freeze over published155 and138 authorities."""
import copy
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
P155=HERE.parent/'2026_10_10_position_error_iter155/protocol.json'
P138=HERE.parent/'2026_10_10_position_error_iter138/protocol.json'
A138=P138.with_name('RESULT_ARCHIVE.json')
AUTHORITIES={P155:'c713a3a4c33a422feedf73915aea1e3e236c7ed1daa6a85064ac0c5d7b79f292',
             P138:'528cb2b510e7ae5692e34c2eaceb99ad7f49385b038ffbd23664a131408f7f97',
             A138:'8d9a0bad74ab8ce78927e8b2d6b21e23306f370d3dea60718920c840e2cdd39c'}
POLICY=dict(members=12,workers=1,threads=1,source_loads_per_member=1,retries=0,
            seed='position-predictive-groups-v1',iq_reads=False,optimizer_calls=0,
            objective_calls=0,references=False)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    for path,expected in AUTHORITIES.items():
        if sha(path)!=expected:raise ValueError('published authority changed: '+str(path))
    previous=json.loads(P155.read_text());older=json.loads(P138.read_text());archive=json.loads(A138.read_text())
    plan={key:copy.deepcopy(previous[key]) for key in ('members','source_sha256','input_sha256','runtime')}
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if sha(ROOT/name)!=expected:raise ValueError('inherited artifact changed: '+name)
    for name,expected in plan['runtime']['sha256'].items():
        if sha(name)!=expected:raise ValueError('inherited runtime changed: '+name)
    if archive['protocol_sha256']!=AUTHORITIES[P138]:raise ValueError('archive protocol differs')
    for path,expected in AUTHORITIES.items():plan['input_sha256'][str(path.relative_to(ROOT))]=expected
    old_members={m['label']:m for m in older['members']}
    if set(old_members)!={m['label'] for m in plan['members']}:raise ValueError('member inventories differ')
    for member in plan['members']:
        old=old_members[member['label']]
        if old['session_id']!=member['binding']['session_id']:raise ValueError('session differs')
        for field in ('session_id','input_manifest_sha256','analysis_manifest_sha256'):
            if old['case_binding']['model_identity'][field]!=member['binding']['model_identity'][field]:
                raise ValueError('support capture/analysis authority differs: '+field)
        if old['case_binding']['expected_input_binding']['observation_order_signature']!=member['binding']['expected_input_binding']['observation_order_signature']:
            raise ValueError('observation inventory changed')
        for suffix in ('.json','.claim.json'):
            name='results/'+member['label']+suffix;path=P138.parent/name
            expected=archive['files'][name]['sha256']
            if sha(path)!=expected:raise ValueError('archived receipt changed: '+name)
            receipt=json.loads(path.read_text())
            if receipt.get('label')!=member['label'] or receipt.get('protocol_sha256')!=AUTHORITIES[P138]:
                raise ValueError('foreign support receipt/claim')
            plan['input_sha256'][str(path.relative_to(ROOT))]=expected
        member['support_path']=str((P138.parent/'results'/(member['label']+'.json')).relative_to(ROOT))
    for name in ('freeze.py','run.py','preparation.py','test_preparation.py'):
        path=HERE/name;plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    path=HERE.parent/'2026_10_10_position_error_iter159/grouping.py'
    plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))]=sha(HERE/'PLAN.md')
    plan.update(policy=copy.deepcopy(POLICY),scope='Consumed metadata grouping only; no likelihood or position outcomes')
    return plan
