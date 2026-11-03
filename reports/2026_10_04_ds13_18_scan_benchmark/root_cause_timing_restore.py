"""Counterfactual single timing restoration at the saved roof; not a refit.

Return one satellite to its prepared selection timing, preserving all other
total shifts, receiver/RF parameters and observations. Separate data likelihood
and timing-prior changes; no priors or published fits are altered.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from root_cause import load_case,make_objective,ARMS

CASES=[('N06',61866),('N06',52487),('N05',68814),('N12',63450),('N16',63550),('N15',59381)]


def single_timing_vector(obj,start,total,index,value):
    total=np.asarray(total).copy();total[index]=value
    common=float(np.mean(total))
    if abs(common)>10:raise ValueError('restoration violates common timing bound')
    restored=np.asarray(start).copy();restored[6]=common
    restored[7:obj.size]=obj.base.basis.T@(total-common)
    return restored,total


def run(root,output):
    rows=[]
    for label,number in CASES:
        data,meta,owners,saved,source,sha=load_case(root,label)
        j=int(np.flatnonzero(data.numbers==number)[0]);mask=owners==number
        for arm in ARMS:
            obj=make_objective(data,float(np.mean(np.unique(data.rf))),arm)
            obj.base.deadline=float('inf')
            start=np.asarray(saved['arms'][arm]['roof']['vector'])
            total=np.asarray(saved['arms'][arm]['roof']['parameters'][6:]).copy()
            original_total=float(total[j])
            restored,total=single_timing_vector(obj,start,total,j,data.initial[6+j])
            evaluations=[]
            for vector in (start,restored):
                value,_=obj.evaluate(vector);prior=obj.base.penalty(vector[:obj.size])[0]
                pred,vis=obj.base.predict(vector[:obj.size]);pred+=(obj.features@vector[obj.size:])[:,None]
                alias=obj.likelihood.alias_hz
                errors=(data.measured-pred[:,j]+alias/2)%alias-alias/2
                evaluations.append(dict(objective=value,prior_nll=prior,data_nll=value-prior,
                    owner_rms_hz=float(np.sqrt(np.mean(errors[mask]**2))),
                    owner_posterior=float(np.mean(obj.likelihood.last_result['row_association_probability'][mask,j])),
                    owned_visible_windows=int(np.sum(vis[mask,j]))))
            before,after=evaluations
            row=dict(scan=label,arm=arm,satellite=number,windows=int(mask.sum()),
                saved_total_shift_s=original_total,restored_total_shift_s=float(total[j]),
                before=before,restored=after,
                change_data_nll=after['data_nll']-before['data_nll'],
                change_prior_nll=after['prior_nll']-before['prior_nll'],
                change_total_nll=after['objective']-before['objective'],source_sha256=sha)
            rows.append(row);print(label,arm,number,'data/prior/total',*[round(row[k],2) for k in ('change_data_nll','change_prior_nll','change_total_nll')],flush=True)
    Path(output).write_text(json.dumps(dict(scope=__doc__,rows=rows),indent=2,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('output');a=p.parse_args();run(a.root,a.output)
