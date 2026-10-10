"""Metadata-only projection preparation. No objective or reference imports."""
import copy
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / '2026_10_10_position_error_iter154'
AUTHORITY_SHA = 'f148eb97a3e789b297c842bb5329bd0162f2e46490c18e056d21adb30d0a6f31'
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
POLICY = dict(members=12, arms=['zero-c','fitted-c'], source_condition='control',
              discovery_policy='native', maximum_joint_calls_per_endpoint=6,
              maximum_joint_calls=144, maximum_seconds_per_endpoint=30,
              workers=2, threads=1, shards=2, members_per_shard=6,
              step_prior_fraction=.001, step_boundary_fraction=.25, minimum_step=1e-6,
              objective_tolerance=1e-6, additive_tolerance=1e-6,
              gradient_absolute_tolerance=1e-5, gradient_relative_tolerance=1e-4,
              stationarity_tolerance=.001, retries=0, optimizer=False,
              quadrature=False, references=False)
FIT_FIELDS = ('vector','clock_coefficients','objective','converged','joint_state')
STATE_FIELDS = ('stage','vector','clock_coefficients','receiver_baseline_hz',
                'clock_nodes_s','satellite_centers_s','total_objective')
OPERATION_FIELDS = ('arm','accepted_stage','satellites','region_source','basin','fit')
STAGES = ('B3','B4','B4W','B5','B7')
NARRATIVE_PATH = 'reports/2026_10_10_position_error_iter154/README.md'
NARRATIVE_OLD = 'ad0748b8e37ea524d7d071890d79dd6563033cee8c72b6211ed9a15649b30d4e'
NARRATIVE_NEW = '2690c1172635be1a52d453df065e733a34e17098b6d87ac8883a7d5be3694b87'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inherited_digest(group, name, expected, actual):
    if expected == actual:
        return expected, None
    if (group == 'input_sha256' and name == NARRATIVE_PATH
            and expected == NARRATIVE_OLD and actual == NARRATIVE_NEW):
        return actual, dict(path=name, old_sha256=expected, new_sha256=actual,
                            reason='Published postseal results', commit='ac82b3a')
    raise ValueError('inherited154 closure changed ' + name)


def project_fit(fit):
    if fit is None:
        return None
    result={key:copy.deepcopy(fit[key]) for key in FIT_FIELDS if key in fit}
    if isinstance(result.get('joint_state'),dict):
        result['joint_state']={key:copy.deepcopy(result['joint_state'][key])
                               for key in STATE_FIELDS if key in result['joint_state']}
    return result


def finite(values):
    return isinstance(values,list) and all(isinstance(v,(int,float)) and not isinstance(v,bool)
                                           and math.isfinite(v) for v in values)


def project_receipt(receipt, label, expected_digest):
    """Reject contract mismatch, never omit members based on error/fit quality."""
    if receipt.get('protocol_sha256')!=expected_digest or receipt.get('label')!=label:
        raise ValueError('foreign selected receipt')
    if receipt.get('status')!='complete' or receipt.get('branch')!='native':
        raise ValueError('unsupported selected source status/branch')
    result={key:copy.deepcopy(receipt[key]) for key in ('status','branch','label','protocol_sha256')}
    result['operational']={}
    result['attempts']={stage:{arm:project_fit(receipt['attempts'][stage].get(arm))
                              for arm in POLICY['arms']} for stage in STAGES}
    for arm in POLICY['arms']:
        source=receipt['operational'][arm]
        operation={key:copy.deepcopy(source[key]) for key in OPERATION_FIELDS}
        operation['fit']=project_fit(source['fit'])
        fit=operation['fit']
        if operation['arm']!=arm or operation['accepted_stage']!='B7':
            raise ValueError('unsupported selected stage/arm')
        if fit!=result['attempts']['B7'][arm]:
            raise ValueError('selected/attempted B7 identity differs')
        if set(FIT_FIELDS)-set(fit) or fit['converged'] is not True:
            raise ValueError('incomplete original selected state')
        state=fit['joint_state']
        if not isinstance(state,dict) or set(STATE_FIELDS)-set(state) or state['stage']!='B7':
            raise ValueError('incomplete original joint state')
        if not finite(fit['vector']) or len(fit['vector'])<8 or not finite(fit['clock_coefficients']):
            raise ValueError('nonfinite selected state')
        if fit['vector']!=state['vector'] or fit['clock_coefficients']!=state['clock_coefficients']:
            raise ValueError('selected/joint state identity differs')
        if not math.isfinite(fit['objective']) or not math.isfinite(state['total_objective']) or abs(fit['objective']-state['total_objective'])>1e-6:
            raise ValueError('selected/joint objective differs')
        if arm=='zero-c' and (fit['vector'][6]!=0 or fit['clock_coefficients'][-2:]!=[0,0]):
            raise ValueError('original zero-c locks violated')
        result['operational'][arm]=operation
    for stage in ('B3','B4'):
        fit=result['attempts'][stage]['fitted-c']
        if fit is None or fit.get('converged') is not True:
            raise ValueError('selected B7 lacks original stage chain')
    seed=result['attempts']['B4']['fitted-c']
    for stage in ('B4W','B5'):
        fit=result['attempts'][stage]['fitted-c']
        if fit is not None and fit.get('converged') is True:
            seed=fit
    if not finite(seed['vector']) or len(seed['vector'])!=len(result['operational']['fitted-c']['fit']['vector']):
        raise ValueError('original B7 seed dimension differs')
    return result


def prepare(canonical_digest):
    authority=PRIOR/'protocol.json'
    if sha(authority)!=AUTHORITY_SHA:
        raise ValueError('published154 protocol changed')
    previous=json.loads(authority.read_text())
    updates=[]
    inherited_inputs=copy.deepcopy(previous['input_sha256'])
    for group in ('source_sha256','input_sha256'):
        for name,expected in previous[group].items():
            accepted,update=inherited_digest(group,name,expected,sha(ROOT/name))
            if update is not None:
                updates.append(update)
                del inherited_inputs[name]
    if previous['runtime']['interpreter']!=INTERPRETER:
        raise ValueError('immutable47e runtime required')
    for name,expected in previous['runtime']['sha256'].items():
        if sha(Path(name))!=expected:
            raise ValueError('inherited runtime changed '+name)
    labels=[m['label'] for m in previous['members']]
    if len(labels)!=12 or len(set(labels))!=12:
        raise ValueError('exact twelve membership required')
    digest=canonical_digest(dict(previous,execution_condition='control'))
    plan=dict(policy=copy.deepcopy(POLICY),members=[],
              source_sha256=copy.deepcopy(previous['source_sha256']),
              input_sha256=inherited_inputs,
              inherited_narrative_updates=updates,
              runtime=copy.deepcopy(previous['runtime']),
              preparation_provenance_sha256={str(authority.relative_to(ROOT)):AUTHORITY_SHA},
              scope='Consumed numerical callback parity only; no outcomes or accuracy claim')
    for update in updates:
        plan['preparation_provenance_sha256'][update['path']]=update['new_sha256']
    projections={}
    for member in previous['members']:
        source=PRIOR/'results'/member['label']/'control/native/result.json'
        projection=project_receipt(json.loads(source.read_text()),member['label'],digest)
        data=(json.dumps(projection,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        path=HERE/'selected'/(member['label']+'.json')
        name=str(path.relative_to(ROOT));expected=hashlib.sha256(data).hexdigest()
        projections[name]=data
        selected={key:copy.deepcopy(member[key]) for key in ('label','dataset','binding')}
        selected.update(selected_path=name,selected_sha256=expected,
                        selected_protocol_digest=digest,
                        selected_source_path=str(source.relative_to(ROOT)),selected_source_sha256=sha(source))
        plan['members'].append(selected)
        plan['input_sha256'][name]=expected
        plan['preparation_provenance_sha256'][str(source.relative_to(ROOT))]=sha(source)
        binding=member['binding']
        for path_key,hash_key in (('document_path','document_sha256'),('imports_path','imports_sha256'),('loader_source','loader_sha256')):
            if path_key in binding:
                bound=ROOT/binding[path_key]
                if sha(bound)!=binding[hash_key]:
                    raise ValueError('clean inference binding changed '+path_key)
                group='source_sha256' if path_key=='loader_source' else 'input_sha256'
                plan[group][binding[path_key]]=binding[hash_key]
    for path in sorted(HERE.glob('*.py')):
        plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    for name in ('conditional.py','math_core.py'):
        path=HERE.parent/'2026_10_10_position_error_iter152'/name
        plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))]=sha(HERE/'PLAN.md')
    return plan,projections


def write_projections(projections):
    """Explicit exclusive publication step, never invoked by prepare()."""
    if any((ROOT/name).exists() for name in projections):
        raise FileExistsError('selected projection already exists; no overwrite')
    for name,data in projections.items():
        path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as file:
            file.write(data)


if __name__=='__main__':
    raise SystemExit('Preparation only; root review before projection writes or freeze')
