"""Matched fixed-geometry fits; no reference or position-evaluation access."""
import argparse
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
import importlib.util


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


PREVIOUS = module('run161_for162', HERE.parent/'2026_10_10_position_error_iter161/run.py')
BASE = PREVIOUS.BASE
HYPOTHESES = ('zero-c', 'fitted-c')
MODES = ('train0', 'train1')
ARMS = ('zero-c', 'fitted-c')


def dependencies(member):
    ports = PREVIOUS.dependencies(member)
    core = module('core162', HERE/'fit_core.py')
    ports.update(execute=core.execute_cell, plain=core.plain)
    return ports


def prepare_member(member, ports):
    prepared = PREVIOUS.prepare_member(member, ports)
    np = ports['np']
    if set(member['hypotheses']) != set(HYPOTHESES):
        raise ValueError('exact two ordinary hypotheses required')
    positions = {}
    for hypothesis in HYPOTHESES:
        binding = member['hypotheses'][hypothesis]
        row = PREVIOUS.read_bound(binding['raw_path'], binding['raw_sha256'])
        claim = PREVIOUS.read_bound(binding['claim_path'], binding['claim_sha256'])
        identity = dict(label=member['label'], mode='full', arm=hypothesis,
                        protocol_sha256=binding['protocol_sha256'])
        if any(row.get(k)!=v or claim.get(k)!=v for k,v in identity.items()):
            raise ValueError('foreign geometry hypothesis')
        position = np.array(binding['position'], dtype=float)
        if (row['status']!='qualified' or not row['audit']['qualified']
                or position.shape!=(2,) or not np.isfinite(position).all()
                or not np.array_equal(position, np.asarray(row['solver']['vector'])[:2])):
            raise ValueError('unqualified or changed geometry hypothesis')
        positions[hypothesis] = position
    prepared['positions'] = positions
    return prepared


def held_score(prepared, mode, fit, ports):
    np = ports['np']; held = '1' if mode=='train0' else '0'
    start = time.monotonic()
    try:
        vector = np.array(fit['vector'], dtype=float, copy=True)
        clock = np.array(fit['clock_coefficients'], dtype=float, copy=True)
        _, _, _, terms = prepared['models']['train'+held].evaluate_joint(vector, clock)
        nll = float(terms.nll); mass = float(np.sum(terms.responsibilities))
        rms = float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>0 else None
        if not np.isfinite(nll) or not np.isfinite(mass) or mass<0 or (rms is not None and not np.isfinite(rms)):
            raise ValueError('nonfinite held score')
        count = prepared['counts'][int(held)]
        result = dict(status='complete', nll=nll, observations=count,
                      nll_per_observation=nll/count, signal_mass=mass, posterior_rms_hz=rms)
    except Exception as error:
        result = dict(status='failed', error=repr(error))
    result['elapsed_s'] = time.monotonic()-start
    return {held:result}


def run_member(member, directory, digest, *, dependency_factory=dependencies,
               prepare=prepare_member, clock=time.monotonic):
    folder=Path(directory)/member['label']; folder.mkdir(parents=True,exist_ok=True)
    identity=dict(label=member['label'],protocol_sha256=digest)
    target,claim=folder/'result.json',folder/'claim.json'
    old=PREVIOUS.existing(target,claim,identity,('complete','failed'))
    keys=[(h,m,a,h+'--'+m+'--'+a) for h in HYPOTHESES for m in MODES for a in ARMS]
    if old is not None:
        if set(old['cells'])!={key for h,m,a,key in keys}:raise ValueError('member inventory differs')
        for h,m,a,key in keys:
            row=PREVIOUS.existing(folder/(key+'.json'),folder/(key+'.claim.json'),
                dict(identity,hypothesis=h,mode=m,arm=a),('qualified','unqualified','failed'))
            if row is None or BASE.sha(folder/(key+'.json'))!=old['cells'][key]['sha256']:
                raise ValueError('missing or changed terminal cell')
        return old
    PREVIOUS.write(claim,identity);begun=clock()
    result=dict(identity,status='failed',cells={},preflight=None)
    ports=None;prepared=None;failure=None
    try:
        ports=dependency_factory(member);prepared=prepare(member,ports)
        result['preflight']=prepared['preflight']
    except Exception as error:
        failure=repr(error);result['preparation_error']=failure
    result['preparation_elapsed_s']=clock()-begun
    for h,m,a,key in keys:
        cid=dict(identity,hypothesis=h,mode=m,arm=a)
        path=folder/(key+'.json');owned=folder/(key+'.claim.json')
        if PREVIOUS.existing(path,owned,cid,('qualified','unqualified','failed')) is not None:
            raise ValueError('unexpected cell behind fresh member claim')
        PREVIOUS.write(owned,cid);start=clock()
        cell=dict(cid,status='failed',scores=None,scores_complete=False)
        try:
            if failure:raise ValueError('preparation failed: '+failure)
            if prepared['identity']()!=prepared['fingerprint']:raise ValueError('model changed before fit')
            vector=prepared['vector'].copy();vector[:2]=prepared['positions'][h]
            cell.update(ports['execute'](prepared['models'][m],vector,prepared['clock'].copy(),
                arm=a,fit_port=ports['fit'],problem_type=ports['problem'],clock=clock))
            if prepared['identity']()!=prepared['fingerprint']:raise ValueError('model mutated during fit')
            if cell['status']=='qualified':
                cell['scores']=held_score(prepared,m,cell['solver'],ports)
                cell['scores_complete']=all(s['status']=='complete' for s in cell['scores'].values())
                if not cell['scores_complete']:cell['score_error']='opposite-fold scoring failed'
                if prepared['identity']()!=prepared['fingerprint']:raise ValueError('model mutated during held score')
        except Exception as error:
            cell['status']='failed';cell['error']=repr(error)
        cell['cell_elapsed_s']=clock()-start
        PREVIOUS.write(path,ports['plain'](cell) if ports else cell)
        result['cells'][key]=dict(status=cell['status'],path=path.name,sha256=BASE.sha(path),
                                  scores_complete=cell['scores_complete'])
    result['status']='complete' if all(c['status']=='qualified' for c in result['cells'].values()) else 'failed'
    result['scores_complete']=all(c['scores_complete'] for c in result['cells'].values())
    result['elapsed_s']=clock()-begun;PREVIOUS.write(target,result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('shard',type=int,choices=(0,1))
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--output',type=Path,default=HERE/'results');args=parser.parse_args()
    plan=json.loads(args.protocol.read_text());freezer=module('freeze162',HERE/'freeze.py')
    BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan)
    for member in plan['members'][args.shard::2]:
        row=run_member(member,args.output,digest)
        print(member['label'],row['status'],flush=True)


if __name__=='__main__':main()
