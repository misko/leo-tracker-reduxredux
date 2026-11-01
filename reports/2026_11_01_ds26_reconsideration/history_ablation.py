"""Separate phase-history from physical-mode history on an accepted identity."""
import argparse,copy
import numpy as np
from reconsider import *
from investigate_ds23_adaptive_failures import phase_widths

def run(case):
    result=read(OUT/case/'result.json')
    if result['selected'] is None:return
    rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected']);h=rec['hypothesis']
    z=read(INPUT/(case+'.json'));d=reconstruct(z);fallback,_=apply_hypothesis(d,z,case,h,OUT/case)
    enriched,receipt=extend_history(d,z,case,set(h['mapping'].values()),OUT/case/'ablation_history')
    full,_=apply_hypothesis(enriched,z,case,h,OUT/case)
    labels=full['problems']['c0'][0].labels;oldwidth=phase_widths(fallback['scan'],labels)[0];newwidth=phase_widths(full['scan'],labels)[0]
    starts={'published':d['problems']['fitted_c'][1],'family_omitted':np.array(read(OUT/case/str(rec['target'])/'screen.json')['cavity']['fitted_c']['x'])};rows=[]
    for name,orbctx,phasectx,widths in [('fallback',fallback,fallback,oldwidth),('phase_history',fallback,full,newwidth),('orbit_history',full,fallback,oldwidth),('full_history',full,full,newwidth)]:
        dd=dict(orbctx,scan=copy.copy(orbctx['scan']),means=phasectx['means'].copy(),problems=dict(orbctx['problems']))
        dd['scan'].diagnostic_phase_width_cache={tuple(labels):widths.copy()}
        for a in ARMS:
            p,x=dd['problems'][a];q,_=build(dd,z,a,p.reference);dd['problems'][a]=(q,x)
            for label,start in starts.items():
                try:
                    r=previous.fit(dd,z,a,start,True,rounds=15);r.pop('tracks');r.pop('proposed_owners');r.update(status='complete',arm=a,start=label,model=name)
                except Exception as exc:r=dict(status='incomplete',arm=a,start=label,model=name,reason=repr(exc))
                rows.append(r);print(case,name,a,label,r.get('error_m'),flush=True)
    write(OUT/case/'history_ablation.json',dict(case=case,rows=rows,history=receipt,phase_width_before=oldwidth,phase_width_after=newwidth,
        prior_mean_before=fallback['means'],prior_mean_after=full['means'],labels=labels,hypothesis=h,scope='matched RF observations, identity, starts, c arms; separate prior components; diagnostic only'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');run(parser.parse_args().case)
