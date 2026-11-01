"""Predeclared gate/receiver sensitivity of an RF-selected reconsideration."""
import argparse
import numpy as np
from reconsider import *

def run(case):
    result=read(OUT/case/'result.json')
    if result['selected'] is None:
        write(OUT/case/'sensitivity.json',dict(case=case,status='no selected replacement'));return
    rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected']);h=rec['hypothesis']
    z=read(INPUT/(case+'.json'));d=reconstruct(z)
    d,history=extend_history(d,z,case,set(h['mapping'].values()),OUT/case/'sensitivity_history')
    dd,receipt=apply_hypothesis(d,z,case,h,OUT/case);start=np.array(result['final']['fitted_c']['x']);rows=[]
    original=previous.feasible_fit
    for method,margin in [('margin_001',.01),('margin_005',.05),('receiver50',0.)]:
        ex.configure('04_receiver_shrink' if method=='receiver50' else 'plain',h['norad'])
        if margin:
            previous.feasible_fit=lambda fun,slacks,*args,**kw:original(fun,lambda x:np.asarray(slacks(x))-margin,*args,**kw)
        for a in ARMS:
            try:
                r=previous.fit(dd,z,a,start,True,rounds=15);r.pop('proposed_owners');r.pop('tracks')
                p,ctx=previous.build(dd,z,a,np.array(r['reference']));minimum=min(ex.gate_slacks(p,np.array(r['x']),ctx['entries']).values())
                r['margin_pass']=minimum>=margin-1e-5;r.update(status='complete',arm=a,method=method,minimum_slack=minimum)
                r['displacement_from_selected_km']=float(np.linalg.norm(np.array(r['x'])-np.array(result['final'][a]['x'])))
            except Exception as exc:r=dict(status='incomplete',method=method,arm=a,reason=repr(exc))
            rows.append(r);print(case,method,a,r.get('error_m'),r.get('qualified'),flush=True)
    write(OUT/case/'sensitivity.json',dict(case=case,selected=result['selected'],rows=rows,scope='diagnostics only; no sensitivity setting chosen from GPS',common_start=start))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');run(parser.parse_args().case)
