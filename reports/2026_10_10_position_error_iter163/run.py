"""Symmetric calibration starts, training-only choice, no reference ports."""
import argparse
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


PREVIOUS=module('run162_for163',HERE.parent/'2026_10_10_position_error_iter162/run.py')
BASE=PREVIOUS.BASE
HYPOTHESES=PREVIOUS.HYPOTHESES
MODES=PREVIOUS.MODES
ARMS=PREVIOUS.ARMS
STARTS=('zero-c','fitted-c')
IO=PREVIOUS.PREVIOUS


def dependencies(member):
    ports=PREVIOUS.dependencies(member)
    core=module('core163',HERE/'fit_core.py')
    selector=module('selection163',HERE/'selection.py')
    ports.update(execute=core.execute_cell,audit_control=core.audit_state,
                 plain=core.plain,choose=selector.choose)
    return ports


def prepare_member(member,ports):
    prepared=PREVIOUS.prepare_member(member,ports)
    np=ports['np'];states={};controls={}
    for source in STARTS:
        binding=member['hypotheses'][source]
        row=IO.read_bound(binding['raw_path'],binding['raw_sha256'])
        states[source]=dict(vector=np.array(row['solver']['vector'],float,copy=True),
                            clock=np.array(row['solver']['clock_coefficients'],float,copy=True))
    expected={h+'--'+m+'--'+a for h in HYPOTHESES for m in MODES for a in ARMS}
    if set(member['controls'])!=expected:raise ValueError('exact control inventory required')
    for key,binding in member['controls'].items():
        h,m,a=key.split('--')
        row=IO.read_bound(binding['raw_path'],binding['sha256'])
        claim=IO.read_bound(binding['claim_path'],binding['claim_sha256'])
        identity=dict(label=member['label'],hypothesis=h,mode=m,arm=a,
                      protocol_sha256=binding['protocol_sha256'])
        if any(row.get(k)!=v or claim.get(k)!=v for k,v in identity.items()):
            raise ValueError('foreign retained control')
        if row['status']!='qualified' or row['audit']['qualified'] is not True:
            raise ValueError('unqualified retained control')
        if not np.array_equal(np.asarray(row['solver']['vector'])[:2],prepared['positions'][h]):
            raise ValueError('control hypothesis differs')
        controls[key]=row
    prepared.update(states=states,controls=controls)
    return prepared


def run_member(member,directory,digest,*,dependency_factory=dependencies,
               prepare=prepare_member,held_score=PREVIOUS.held_score,clock=time.monotonic):
    folder=Path(directory)/member['label'];folder.mkdir(parents=True,exist_ok=True)
    identity=dict(label=member['label'],protocol_sha256=digest)
    target,claim=folder/'result.json',folder/'claim.json'
    keys=[(h,m,a,h+'--'+m+'--'+a) for h in HYPOTHESES for m in MODES for a in ARMS]
    old=IO.existing(target,claim,identity,('complete','failed'))
    if old is not None:
        expected={key for h,m,a,key in keys}
        if set(old['cells'])!=expected or set(old['attempts'])!={key+'--start-'+s for key in expected for s in STARTS}:
            raise ValueError('terminal inventory differs')
        for group in ('cells','attempts'):
            for key,record in old[group].items():
                h,m,a=key.split('--')[:3]
                bound=dict(identity,hypothesis=h,mode=m,arm=a)
                if group=='attempts':bound['start_source']=key.split('--start-')[1]
                value=IO.existing(folder/(key+'.json'),folder/(key+'.claim.json'),bound,
                                  ('qualified','unqualified','failed'))
                if value is None or BASE.sha(folder/(key+'.json'))!=record['sha256']:
                    raise ValueError('changed terminal artifact')
        return old
    IO.write(claim,identity);begun=clock()
    result=dict(identity,status='failed',cells={},attempts={},preflight=None)
    ports=prepared=None;failure=None
    try:
        ports=dependency_factory(member);prepared=prepare(member,ports)
        result['preflight']=prepared['preflight']
    except Exception as error:
        failure=repr(error);result['preparation_error']=failure
    result['preparation_elapsed_s']=clock()-begun

    def unchanged():
        if prepared['identity']()!=prepared['fingerprint']:raise ValueError('model fingerprint changed')

    def seal(key,bound,value,group):
        path=folder/(key+'.json');owned=folder/(key+'.claim.json')
        if path.exists():raise ValueError('unexpected preexisting result')
        # Claim must be acquired before any work; this only writes its result.
        IO.write(path,ports['plain'](value) if ports else value)
        result[group][key]=dict(status=value['status'],path=path.name,sha256=BASE.sha(path))

    for h,m,a,key in keys:
        cid=dict(identity,hypothesis=h,mode=m,arm=a)
        owned=folder/(key+'.claim.json');path=folder/(key+'.json')
        if IO.existing(path,owned,cid,('qualified','unqualified','failed')) is not None:
            raise ValueError('unexpected selected result behind fresh claim')
        IO.write(owned,cid);cell=dict(cid,status='failed',scores=None,scores_complete=False,
                                    selected_source=None,control_retained=False,candidates={})
        cell_begun=clock()
        candidates={};control_failure=None
        try:
            if failure:raise ValueError('preparation failed: '+failure)
            unchanged();control=prepared['controls'][key];fit=control['solver']
            audit=ports['audit_control'](prepared['models'][m],
                ports['np'].array(fit['vector'],float,copy=True),
                ports['np'].array(fit['vector'],float,copy=True),
                ports['np'].array(fit['clock_coefficients'],float,copy=True),fit['objective'],
                arm=a,problem_type=ports['problem'],clock=clock)
            audit['solver']=fit
            unchanged();candidates['control']=audit
            cell['control_audit']=audit
            if audit['status']!='qualified':raise ValueError('retained control fresh audit failed')
        except Exception as error:
            control_failure=repr(error)
            candidates.setdefault('control',dict(status='failed',error=control_failure))
            cell['control_admission_error']=control_failure
        for source in STARTS:
            ak=key+'--start-'+source;aid=dict(cid,start_source=source)
            ap=folder/(ak+'.json');ac=folder/(ak+'.claim.json')
            if IO.existing(ap,ac,aid,('qualified','unqualified','failed')) is not None:
                raise ValueError('unexpected attempt behind fresh member claim')
            IO.write(ac,aid);start=clock();attempt=dict(aid,status='failed')
            try:
                if failure:raise ValueError('preparation failed: '+failure)
                if control_failure:raise ValueError('control admission failed: '+control_failure)
                unchanged();vector=prepared['states'][source]['vector'].copy()
                coefficients=prepared['states'][source]['clock'].copy()
                vector[:2]=prepared['positions'][h]
                if a=='zero-c':vector[6]=0.;coefficients[-2:]=0.
                attempt.update(ports['execute'](prepared['models'][m],vector,coefficients,
                    arm=a,fit_port=ports['fit'],problem_type=ports['problem'],clock=clock))
                unchanged()
            except Exception as error:attempt.update(status='failed',error=repr(error))
            attempt['attempt_elapsed_s']=clock()-start
            seal(ak,aid,attempt,'attempts');candidates[source]=attempt
        cell['candidates']=candidates
        try:
            if failure:raise ValueError('preparation failed: '+failure)
            if control_failure:raise ValueError('control admission failed: '+control_failure)
            unchanged();selected=ports['choose'](candidates)
            cell['selected_source']=selected;cell['control_retained']=selected=='control'
            if selected is not None:
                winner=candidates[selected]
                cell.update(status='qualified',solver=winner['solver'],audit=winner['audit'])
                try:
                    cell['scores']=held_score(prepared,m,winner['solver'],ports)
                except Exception as error:
                    held='1' if m=='train0' else '0'
                    cell['scores']={held:dict(status='failed',error=repr(error))}
                cell['scores_complete']=all(s['status']=='complete' for s in cell['scores'].values())
                unchanged()
        except Exception as error:cell.update(status='failed',error=repr(error))
        cell['cell_elapsed_s']=clock()-cell_begun
        seal(key,cid,cell,'cells')
    result['status']='complete' if all(r['status']=='qualified' for r in result['cells'].values()) else 'failed'
    result['scores_complete']=all(json.loads((folder/r['path']).read_text()).get('scores_complete',False)
                                  for r in result['cells'].values())
    result['elapsed_s']=clock()-begun;IO.write(target,result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('shard',type=int,choices=(0,1))
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--output',type=Path,default=HERE/'results');args=parser.parse_args()
    plan=json.loads(args.protocol.read_text());freezer=module('freeze163',HERE/'freeze.py')
    BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan)
    for member in plan['members'][args.shard::2]:
        row=run_member(member,args.output,digest);print(member['label'],row['status'],flush=True)


if __name__=='__main__':main()
