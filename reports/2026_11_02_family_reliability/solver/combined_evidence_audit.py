"""Independent full-native-union replay of sealed combined endpoints.

No fit, model selection, or evaluation truth is used. Output is a final audit,
leaving frozen runners and their provisional results untouched.
"""
import hashlib,importlib.util,json,sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
sys.path.insert(0,str(BASE))
import combined as driver
from qualify_combined import qualifies
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo06_science.common import read,write
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def inventory(d,p):
    groups={'curved':[],'conditional_entries':[],'phase_mixture_families':[]};owners={}
    def append(kind,ids,norad):
        for oid in ids:
            if oid in owners:raise ValueError('native ID duplicated across fitted likelihood pieces')
            groups[kind].append(oid);owners[oid]=int(norad)
    for row,i,sl in zip(p.rows,p.members,p.slices):
        append('curved',[o for o,k in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl]) if k],row['candidate_norad'])
    for ent in d['entries']:append('conditional_entries',ent['observation_ids'],ent['norad'])
    for f in d['families']:
        for ent in f.entries:append('phase_mixture_families',ent['observation_ids'],ent['norad'])
    groups={k:sorted(v) for k,v in groups.items()}
    return dict(ids=sorted(owners),groups=groups,owners=owners,
        counts={k:len(v) for k,v in groups.items()},ids_sha256=digest(sorted(owners)),owners_sha256=digest(owners))

def audit(case):
    out=BASE/'combined'/case;plan=read(out/'plan.json')
    endpoints=sorted([*out.glob('*-c0.json'),*out.glob('*-fitted_c.json')])
    rows=[read(p) for p in endpoints]
    bank=driver.OLD/'eval'/case/'input/history-bank.json'
    # The complete-history cache must exist when new history was required.
    # This callback intentionally fails rather than doing a fresh collection.
    def no_collection(request):raise RuntimeError('audit cannot collect new history')
    e.configure(driver.DATA,out,collect_history=no_collection);e.ROOTS['DS26']=driver.DATA
    d,z,replay=e.load_case(case)
    union=e.active_ids(d)|{h['norad'] for h in plan['hypotheses']}
    hd,history=e.complete_history(d,z,case,union,out/'shared_history')
    assert history==plan['history'],'causal-history union no longer matches sealed plan'
    baseline={arm:inventory(d,p) for arm,(p,x) in d['problems'].items()}
    for arm,b in baseline.items():
        assert b['owners']==z['baseline_owners'][arm], 'baseline fitted union differs from frozen published ownership'
    results=[]
    for h in plan['hypotheses']:
        base=hd if h['name']=='incumbent' else e.remap(hd,z,case,h)
        for scale in (1.,2.,4.):
            dd=driver.candidate_context(base,z,scale,h['norad'])
            for arm in e.ARMS:
                row=next(r for r in rows if (r['hypothesis'],r['SD_scale'],r['arm'])==(h['name'],scale,arm))
                p,ctx=e.build(dd,z,arm,np.asarray(row['reference']));x=np.asarray(row['x'])
                actual=inventory(ctx,p);old=baseline[arm]
                preserved=actual['ids']==old['ids']
                unrelated_fit=[o for o,n in old['owners'].items() if n!=plan['target'] and actual['owners'].get(o)!=n]
                target_fit=[o for o,n in old['owners'].items() if n==plan['target'] and actual['owners'].get(o)!=n]
                # Independently replay the inherited graph membership proposal.
                _,_,_,proposed=memberships(original_graph_view(p,len(p.scan.index)),x,ctx['entries'])
                for f in ctx['families']:
                    for ent in f.entries:proposed.update({o:ent['norad'] for o in ent['observation_ids']})
                lost=[o for o in z['baseline_owners'][arm] if o not in proposed]
                changed=[o for o,n in z['baseline_owners'][arm].items() if o in proposed and proposed[o]!=n]
                unrelated_proposed=[o for o in changed if z['baseline_owners'][arm][o]!=plan['target']]
                delta=objective(p,ctx,x)-row['objective']
                assert abs(delta)<1e-4,'sealed endpoint objective failed replay'
                assert proposed==row['proposed_owners'],'sealed membership proposal failed replay'
                assert preserved and not unrelated_fit,'full likelihood union or unrelated fitted identity changed'
                final_qualified=qualifies(row)
                if final_qualified:
                    assert not lost and not unrelated_proposed,'qualified endpoint changes unrelated published owners'
                results.append(dict(hypothesis=h['name'],norad=h['norad'],SD_scale=scale,arm=arm,
                    final_qualified=final_qualified,full_native_union_preserved=preserved,
                    native_counts=actual['counts'],native_union_count=len(actual['ids']),
                    native_union_sha256=actual['ids_sha256'],fitted_identity_sha256=actual['owners_sha256'],
                    unrelated_fitted_identity_changes=unrelated_fit,target_fitted_identity_changes=len(target_fit),
                    unadopted_proposal_lost_ids=lost,unadopted_proposal_unrelated_reassigned_ids=unrelated_proposed,
                    unadopted_proposal_target_reassigned_count=len(changed)-len(unrelated_proposed),
                    unadopted_proposal_added_count=len(set(proposed)-set(z['baseline_owners'][arm])),
                    objective_replay_difference=delta,proposal_owner_sha256=digest(proposed)))
    result=dict(case=case,status='passed',scope='full fitted-native-union and unrelated identity/owner audit; no truth or new fitting',
        plan_sha256=driver.sha(out/'plan.json'),combined_endpoint_sha256={p.name:driver.sha(p) for p in endpoints},
        shared_history=history,baseline=baseline,models=results,
        all_full_native_unions_preserved=all(r['full_native_union_preserved'] for r in results),
        all_unrelated_fitted_identities_preserved=all(not r['unrelated_fitted_identity_changes'] for r in results),
        qualified_models_no_unrelated_proposed_owner_changes=all(not r['unadopted_proposal_lost_ids'] and not r['unadopted_proposal_unrelated_reassigned_ids'] for r in results if r['final_qualified']))
    write(ROOT/f'combined_evidence_audit_{case}.json',result)
    print(case,'audited',len(results),'arm endpoints; full union',len(baseline['c0']['ids']),'pass',flush=True)

if __name__=='__main__':
    for case in ('DS26-0070','DS26-0309'):audit(case)
