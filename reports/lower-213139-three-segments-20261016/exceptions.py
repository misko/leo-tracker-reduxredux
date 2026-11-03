"""Inspect the remaining pointwise competitors after the timing/q diagnostic."""
import json
import numpy as np
from timing_trials import restore
from search import ROOT
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def main():
    a,ctx,full,model,fit,audit=restore();endpoint=np.load(ROOT/'trial-endpoint.npz')
    trial=json.loads((ROOT/'timing-trials.json').read_text());v=endpoint['vector'];n=endpoint['nuisance']
    ev,details=model.evaluate_details(v,n);terms=ev[3];best=terms.responsibilities.argmax(axis=1)
    associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    correction=model.original.correction(v,n[:model.clock_count])
    np.testing.assert_allclose(correction,a['correction'],atol=1e-9,rtol=0)
    pred=predict_orbits(model.bank,model.observations,model.prior,v[:2],v[7]+model.basis@v[8:],derivatives=False)[0]
    r=circular(model.observations.measured_hz[:,None]-correction[:,None]-pred)
    nums=list(model.bank.numbers);records=[]
    for group in trial['profiles']:
        k=nums.index(group['satellite'])
        for row in group['rows']:
            if associated[row] and best[row]==k:continue
            j=int(best[row]);records.append(dict(group=group['group'],row=row,time_s=float(a['times'][row]),
                margin=float(a['margin'][row]),proposed_satellite=group['satellite'],
                proposed_residual_hz=float(r[row,k]),proposed_probability=float(terms.responsibilities[row,k]),
                clutter_probability=float(terms.clutter_probability[row]),associated=bool(associated[row]),
                best_satellite=int(nums[j]),best_residual_hz=float(r[row,j]),best_probability=float(terms.responsibilities[row,j])))
    report=dict(records=records,qualification='Post-diagnostic pointwise competition. Proposed identities '
        'are coherent-track hypotheses, not independent labels. A competing assignment can reflect '
        'a crossing, a different singleton observation, or residual/weight differences.')
    (ROOT/'exceptions.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
