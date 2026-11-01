"""RF-only follow-up: sensitivity to missing-history phase prior width.

Triggered for every nominated candidate absent from the original bank, not by
position error. Hold observations, means, physical modes, starts and gates fixed.
"""
import argparse
import numpy as np
import prototype as p

def run(case):
    z=p.read(p.INPUT/(case+'.json'));d=p.reconstruct(z);old=p.SUSPECT[case]
    cavity=p.PRIOR/case/f'extended_omit_{old}.json'
    if not cavity.exists():cavity=p.PRIOR/case/f'omit_{old}.json'
    starts={'published':d['problems']['fitted_c'][1],'family_omitted':np.array(p.read(cavity)['fitted_c']['x'])}
    original_build=p.build
    for new in p.nominees(case):
        if new in d['scan'].norads:continue
        for factor in (2.,4.):
            dd=p.candidate(d,z,case,new,1.)
            j=list(dd['scan'].norads).index(new)
            def scaled_build(*args,**kwargs):
                problem,context=original_build(*args,**kwargs);k=problem.labels.index(j)
                # The standardized mean was constructed before this alteration;
                # require exact zero so the physical prior mean remains unchanged.
                assert context['means'][k]==0.
                problem.phase_sigma=problem.phase_sigma.copy();problem.phase_sigma[k]*=factor
                return problem,context
            p.build=scaled_build;rows=[]
            try:
                for a in p.ARMS:
                    for name,start in starts.items():
                        r=p.fit(dd,z,a,start,True);r.update(arm=a,start=name);rows.append(r)
                        print(case,new,'prior width',factor,a,name,round(r['error_m']/1000,3),r['qualified'],flush=True)
            finally:p.build=original_build
            p.write(p.OUT/case/f'fallback-prior-{new}-x{factor:g}.json',dict(case=case,norad=new,factor=factor,rows=rows,
                scope='phase SD only for missing-history candidate; normalized mean remains zero; no age score, no other prior/weight/gate change'))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('case');run(a.parse_args().case)
