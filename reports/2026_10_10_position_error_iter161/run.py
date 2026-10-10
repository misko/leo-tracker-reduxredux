"""Sealed grouped-training fits; no reference coordinates or evaluation ports."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODES = ('full', 'train0', 'train1')
ARMS = ('zero-c', 'fitted-c')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BASE = module('base155_for161', HERE.parent/'2026_10_10_position_error_iter155/run.py')


def read_bound(path, expected):
    path = ROOT/path
    if BASE.sha(path) != expected:
        raise ValueError('Bound input changed: '+str(path))
    return json.loads(path.read_text())


def dependencies(member):
    # Invoked only after the full source/input/runtime closure check.
    import numpy as np
    from leo.analysis.hard60_dynamic_rf import fit
    sys.path.insert(0, str(HERE.parent/'2026_10_10_position_error_iter155'))
    ports = BASE.dependencies(member)
    rows = module('rows159_for161', HERE.parent/'2026_10_10_position_error_iter159/rows.py')
    core = module('core161', HERE/'fit_core.py')
    ports.update(np=np, row_objective=rows.RowObjective, prior_terms=rows.prior_terms,
                 fit=fit, execute=core.execute_cell, plain=core.plain,
                 fingerprint=BASE.fingerprint)
    return ports


def prepare_member(member, ports):
    np = ports['np']
    selected = read_bound(member['selected_path'], member['selected_sha256'])
    if (selected.get('label') != member['label'] or selected.get('branch') != 'native'
            or selected.get('protocol_sha256') != member['selected_protocol_digest']):
        raise ValueError('Foreign original selected receipt')
    folds = read_bound(member['fold_path'], member['fold_sha256'])
    if (folds.get('label') != member['label'] or folds.get('status') != 'complete'
            or folds.get('protocol_sha256') != member['fold_protocol_digest']):
        raise ValueError('Foreign or incomplete fold receipt')
    groups = folds['groups']
    if (groups['session_id'] != member['binding']['session_id']
            or groups['observation_order_signature'] != member['binding']['expected_input_binding']['observation_order_signature']):
        raise ValueError('Fold observation identity differs')
    case = ports['loader'](member['binding'])
    endpoints = {arm: ports['reconstruct'](case, selected, arm, construct=ports['construct'],
        components=ports['components'], problem_type=ports['problem']) for arm in ARMS}
    fingerprints = {arm: ports['fingerprint'](endpoints[arm]['model']) for arm in ARMS}
    if fingerprints['zero-c'] != fingerprints['fitted-c']:
        raise ValueError('Historical c-arm model definitions differ')
    common = endpoints['zero-c']; full = common['model']
    vector, clock = common['vector'].copy(), common['clock'].copy()
    if vector[6] != 0 or np.any(clock[-2:] != 0):
        raise ValueError('Original zero-c start is not exactly locked')
    count = len(full.observations.window_ids)
    indices = [groups['grouping']['folds'][str(i)] for i in (0,1)]
    if (any(not v or any(isinstance(i,bool) or not isinstance(i,int) for i in v) for v in indices)
            or sorted(indices[0]+indices[1]) != list(range(count))
            or any(v != sorted(v) for v in indices)):
        raise ValueError('Folds do not partition all original rows exactly')
    models = {'full':full, **{'train'+str(i):ports['row_objective'](full, indices[i]) for i in (0,1)}}
    def identity():
        return {name:ports['fingerprint'](model if name=='full' else model._delegate)
                for name, model in models.items()}
    frozen = identity()
    evaluated = [models[name].evaluate_joint(vector.copy(), clock.copy()) for name in MODES]
    prior = ports['prior_terms'](full, vector, clock)
    deltas = []
    for index in range(3):
        values = [np.asarray(value[index]) for value in evaluated]
        if not all(np.isfinite(v).all() for v in values) or not np.isfinite(prior[index]).all():
            raise ValueError('Nonfinite decomposition preflight')
        delta = float(np.max(np.abs(values[0]-(values[1]+values[2]-prior[index]))))
        deltas.append(delta)
    saved_delta = float(evaluated[0][0]-common['saved_objective'])
    if max(deltas)>1e-6 or not np.isfinite(saved_delta) or abs(saved_delta)>1e-6:
        raise ValueError('Full/fold/prior or original zero objective mismatch')
    term_deltas={}
    for field in ('responsibilities','residual_hz','prediction_gradient'):
        full_terms=getattr(evaluated[0][3],field,None)
        if full_terms is None:
            raise ValueError('Required likelihood term unavailable: '+field)
        for i in (0,1):
            a=np.asarray(full_terms)[indices[i]]
            b=np.asarray(getattr(evaluated[i+1][3],field))
            if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
                raise ValueError('Invalid subset likelihood terms: '+field)
            delta=float(np.max(abs(a-b),initial=0.))
            term_deltas[field+':'+str(i)]=delta
            if delta>1e-6:raise ValueError('Subset likelihood term parity failed: '+field)
    if identity()!=frozen:
        raise ValueError('Model mutated during decomposition preflight')
    return dict(models=models, vector=vector, clock=clock, identity=identity, fingerprint=frozen,
                counts=[len(v) for v in indices], preflight=dict(calls=3,
                decomposition_max_abs=deltas, original_zero_objective_delta=saved_delta,
                likelihood_term_max_abs=term_deltas,
                matched_model=True, local_center=vector[:2].tolist(), local_radius_km=25.))


def fixed_scores(prepared, fit, ports):
    np=ports['np']; result={}
    vector=np.asarray(fit['vector']); clock=np.asarray(fit['clock_coefficients'])
    for i in (0,1):
        begun=time.monotonic()
        try:
            _, _, _, terms=prepared['models']['train'+str(i)].evaluate_joint(vector.copy(),clock.copy())
            mass=float(np.sum(terms.responsibilities)); nll=float(terms.nll)
            rms=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>0 else None
            if not np.isfinite(nll) or not np.isfinite(mass) or mass<0 or (rms is not None and not np.isfinite(rms)):
                raise ValueError('Nonfinite fixed-parameter score')
            result[str(i)]=dict(status='complete', nll=nll, observations=prepared['counts'][i],
                nll_per_observation=nll/prepared['counts'][i], signal_mass=mass, posterior_rms_hz=rms)
        except Exception as error:
            result[str(i)]=dict(status='failed',error=repr(error))
        result[str(i)]['elapsed_s']=time.monotonic()-begun
    return result


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def existing(path, claim, identity, statuses):
    if not path.exists():
        if claim.exists():
            raise FileExistsError('Unresolved exclusive claim; no automatic retry: '+str(claim))
        return None
    value=json.loads(path.read_text()); owner=json.loads(claim.read_text())
    if (any(value.get(k)!=v or owner.get(k)!=v for k,v in identity.items())
            or value.get('status') not in statuses):
        raise ValueError('Foreign or nonterminal receipt/claim')
    return value


def run_member(member, directory, digest, *, dependency_factory=dependencies,
               prepare=prepare_member, clock=time.monotonic):
    folder=Path(directory)/member['label']; folder.mkdir(parents=True,exist_ok=True)
    identity=dict(label=member['label'],protocol_sha256=digest)
    target,claim=folder/'result.json',folder/'claim.json'
    old=existing(target,claim,identity,('complete','failed'))
    if old is not None:
        for mode in MODES:
            for arm in ARMS:
                key=mode+'--'+arm
                if existing(folder/(key+'.json'),folder/(key+'.claim.json'),dict(identity,mode=mode,arm=arm),
                            ('qualified','unqualified','failed')) is None:
                    raise ValueError('Missing cell behind terminal member')
                if BASE.sha(folder/(key+'.json'))!=old['cells'][key]['sha256']:
                    raise ValueError('Cell hash differs from member receipt')
        return old
    write(claim,identity);begun=clock()
    result=dict(identity,status='failed',cells={},preflight=None)
    prepared=None;ports=None;failure=None
    try:
        ports=dependency_factory(member); prepared=prepare(member,ports)
        result['preflight']=prepared['preflight']
    except Exception as error:
        failure=repr(error);result['preparation_error']=failure
    result['preparation_elapsed_s']=clock()-begun
    for mode in MODES:
        for arm in ARMS:
            key=mode+'--'+arm; cid=dict(identity,mode=mode,arm=arm)
            path=folder/(key+'.json'); owned=folder/(key+'.claim.json')
            if existing(path,owned,cid,('qualified','unqualified','failed')) is not None:
                raise ValueError('Unexpected preexisting cell in a fresh member claim')
            write(owned,cid);start=clock()
            cell=dict(cid,status='failed',scores=None)
            try:
                if failure: raise ValueError('Preparation failed: '+failure)
                if prepared['identity']()!=prepared['fingerprint']:
                    raise ValueError('Model differs before cell')
                cell.update(ports['execute'](prepared['models'][mode],prepared['vector'].copy(),
                    prepared['clock'].copy(),arm=arm,fit_port=ports['fit'],problem_type=ports['problem'],clock=clock))
                if prepared['identity']()!=prepared['fingerprint']:
                    raise ValueError('Model mutated during fit/audit')
                if cell['status']=='qualified':
                    cell['scores']=fixed_scores(prepared,cell['solver'],ports)
                    if any(row['status']!='complete' for row in cell['scores'].values()):
                        cell['score_error']='Fixed-parameter fold scoring failed; fit qualification preserved'
                    if prepared['identity']()!=prepared['fingerprint']:
                        raise ValueError('Model mutated during fold scoring')
            except Exception as error:
                cell['status']='failed';cell['error']=repr(error)
            cell['cell_elapsed_s']=clock()-start
            write(path,ports['plain'](cell) if ports else cell)
            result['cells'][key]=dict(status=cell['status'],path=path.name,sha256=BASE.sha(path))
            result['cells'][key]['scores_complete']=bool(cell['scores'] is not None and
                all(row['status']=='complete' for row in cell['scores'].values()))
    result['status']='complete' if all(v['status']=='qualified' for v in result['cells'].values()) else 'failed'
    result['scores_complete']=all(v['scores_complete'] for v in result['cells'].values())
    result['elapsed_s']=clock()-begun
    write(target,result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('shard',type=int,choices=(0,1))
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--output',type=Path,default=HERE/'results');args=parser.parse_args()
    plan=json.loads(args.protocol.read_text())
    freezer=module('freeze161',HERE/'freeze.py')
    BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan)
    for member in plan['members'][args.shard::2]:
        row=run_member(member,args.output,digest)
        print(member['label'],row['status'],flush=True)


if __name__=='__main__':main()
