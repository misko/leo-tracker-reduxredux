"""Strict paired position/phase starts, reusing identical fitted-c evaluations."""
import argparse, copy, signal, time
import numpy as np
from diagnose import ROOT,ARMS,load,read,write,refit,error,gates,e

def run(case):
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded matched-start control timeout')));signal.alarm(650)
    out=ROOT/case;d,z,_=load(case);plan=read(out/'fit-plan.json')
    shared_x=d['problems']['fitted_c'][1].copy();shared_reference=d['problems']['fitted_c'][0].reference.copy()
    dd=dict(d,problems=dict(d['problems']));old=copy.copy(d['problems']['c0'][0]);old.reference=shared_reference.copy();dd['problems']['c0']=(old,shared_x)
    write(out/'matched-start-plan.json',dict(position_start=shared_x,phase_reference_start=shared_reference,selection='published fitted-c RF endpoint, no GPS selection',
        arms_start_identical=True,rounds=15,maxfun=140,reused_fitted_c='same starting position/reference, observations, priors, and budgets as saved-arm fitted-c result'))
    # Bounded follow-up: common-start continuation everywhere; only three
    # predeclared headline omission controls, never selected by this rerun.
    headline={'DS26-0070':62320,'DS26-0309':60148,'DS26-0044':57414}
    tests=[('continue',None,1.,shared_x)]
    if case in headline:
        n=headline[case];tests.append((f'omit_{n}',n,1.,shared_x))
    try:
        for tag,n,scale,start in tests:
            target=out/('matched_'+tag+'.json')
            if target.exists():continue
            row=refit(dd,z,'c0',start,n,scale,rounds=15);row['error_m']=error(np.asarray(row['x']))
            p,ctx=e.build(dd,z,'c0',np.asarray(row['reference']),n,scale);row.update(gates(p,ctx,np.asarray(row['x']),z,'c0'))
            row['start_policy']='identical c0/fitted-c position and phase-reference starts';row['qualification_scope']='matched-start diagnostic, not approved family removal'
            write(out/('matched_'+tag+'-c0.json'),row)
            other=read(out/(tag+'-fitted_c.json'));other=dict(other,start_policy=row['start_policy'],reused_identical_fitted_c_fit=True)
            write(out/('matched_'+tag+'-fitted_c.json'),other);write(target,dict(c0=row,fitted_c=other))
            print(case,tag,'matched',round(row['error_m'],1),row['phase_closed'],row['all_gates_pass'],round(time.monotonic()-began),flush=True)
        write(out/'matched-completion.json',dict(status='complete',seconds=time.monotonic()-began))
    except Exception as exc:
        write(out/'matched-completion.json',dict(status='incomplete',reason=repr(exc),seconds=time.monotonic()-began));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');run(p.parse_args().case)
