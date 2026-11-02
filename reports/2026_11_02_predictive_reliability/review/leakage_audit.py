"""Real-context held-CFO perturbation audit: evaluations only, no optimizer.

Fixed graph/aliases/identities are conditioning inputs. This checks numerical
training posteriors after preprocessing, not upstream discovery independence.
"""
import copy,hashlib,importlib.util,json,signal,time
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
spec=importlib.util.spec_from_file_location('independent_predictive_engine',BASE/'predictive/engine.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def perturbed(d,selected,delta):
    scan=copy.copy(d['scan']);scan.tracks=[dict(t,values=np.asarray(t['values']).copy()) for t in scan.tracks]
    p=d['problems']['fitted_c'][0]
    for i,sl in zip(p.members,p.slices):
        local=np.flatnonzero(selected[sl])
        scan.tracks[i]['values'][local]+=delta*(1.+.13*np.sin(np.arange(len(local))))
    return dict(d,scan=scan)

def build(d,z,scale,target,train,arm):
    dd=m.family.candidate_context(d,z,scale,family=target)
    dd,zz,receipt=m.adapter.prepare_context(dd,z,train)
    initial=m.adapter.initial_conditions(dd)
    p,ctx=e.build(dd,zz,arm,initial['reference'])
    return p,ctx,receipt

def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s no-fit leakage-audit cap')))
    signal.alarm(120)
    protocol=read(BASE/'protocol.json');plan=read(BASE/'predictive/plan.json');results=[]
    for path,h in protocol['source_sha256'].items():assert sha(path)==h,'frozen source changed'
    for record in plan['cases']:
        case=record['case'];path=Path(record['input_path']);e.configure(path.parent.parent,ROOT/'local_engine');e.ROOTS[case[:4]]=path.parent.parent
        d,z,_=e.load_case(case);a=m.native(d['problems']['fitted_c'][0])
        splits=[record['partitions'][0]]+[s for s in record['partitions'] if s['kind']=='family_receiver' and s['eligible']]
        for split in splits:
            train=np.isin(a['ids'],split['train_ids']);held=np.isin(a['ids'],split['held_ids'])
            changed=perturbed(d,held,1e5)
            for scale in (1.,4.):
                for arm in ('c0','fitted_c'):
                    p,ctx,receipt=build(d,z,scale,record['family'],train,arm)
                    q,qctx,qreceipt=build(changed,z,scale,record['family'],train,arm)
                    assert receipt==qreceipt
                    assert np.array_equal(p.values[train],q.values[train])
                    assert np.max(abs(p.values[held]-q.values[held]))>1e4
                    comparisons=[]
                    for x in (np.zeros(2),np.array([.25,-.5])):
                        c=p.calculate(x);cc=q.calculate(x);differences={}
                        for key in ('negative_twice_elbo','coefficient','latent_coefficient','noise_precision',
                            'coefficient_prior_precision','quadratic','logvolume','normalization_constant',
                            'precision_iterations','final_log_precision_change','features'):
                            differences[key]=float(np.max(abs(np.asarray(c[key])-np.asarray(cc[key]))))
                            assert differences[key]==0.,f'{case}/{split["name"]}/{arm}/SD{scale}:held leakage in {key}'
                        delta=objective(p,ctx,x)-objective(q,qctx,x)
                        assert delta==0.,'held-CFO changes training objective'
                        comparisons.append(dict(position_km=x,maximum_differences=differences,objective_difference=delta))
                    # Positive control: actual training CFO changes must reach the
                    # tested numerical objective, rather than an ignored copy.
                    damaged=perturbed(d,train,1e4);r,rctx,_=build(damaged,z,scale,record['family'],train,arm)
                    training_change=objective(r,rctx,np.zeros(2))-objective(p,ctx,np.zeros(2))
                    assert abs(training_change)>1e-5,'training perturbation did not reach objective'
                    results.append(dict(case=case,split=split['name'],arm=arm,SD_scale=scale,
                        held_points=int(held.sum()),training_points=int(train.sum()),held_perturbation_hz=1e5,
                        evaluations=comparisons,training_perturbation_objective_change=training_change,status='passed'))
    signal.alarm(0)
    output=dict(status='passed',scope='real-context fixed-position evaluations; no optimizer or evaluation geography',
        protocol_sha256=sha(BASE/'protocol.json'),plan_sha256=sha(BASE/'predictive/plan.json'),
        review_source_sha256=sha(Path(__file__)),cells=len(results),position_evaluations=2*len(results),
        all_held_perturbation_training_differences_exactly_zero=True,all_training_positive_controls_change_objective=True,
        seconds=time.monotonic()-began,results=results)
    write(ROOT/'leakage_audit.json',output)
    print(json.dumps({k:output[k] for k in ('status','cells','position_evaluations','seconds')}),flush=True)

if __name__=='__main__':main()
