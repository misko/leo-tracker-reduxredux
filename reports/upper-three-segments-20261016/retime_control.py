"""Evaluate a training-informed timing edit under the complete saved objective."""
import json
import numpy as np
from search import ROOT,observations
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz');ctx=json.loads((ROOT/'context.json').read_text())
    shape=json.loads((ROOT/'shape-controls.json').read_text());groups=[g for g in shape['groups'] if g['part']==0]
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2');job,doc,terminal,stages=store.plot_evidence('73c4b28b4f002e0d2154bab2f67457b6')
    source=load_input(doc);prepared,nodes=prepare_views(source)
    prior=RegionalPrior(**ctx['prior']);bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities'])
    nums=terminal['candidate_numbers'];lookup={int(n):j for j,n in enumerate(bank.numbers)}
    model,fit,audit=selected_model(prepared,bank.select([lookup[n] for n in nums]),prior,nodes,terminal,stages)
    v,n=(np.array(fit[k]) for k in ['vector','nuisance']);tau=v[7]+model.basis@v[8:]
    group=groups[1];rows=np.array(group['rows']);obs=observations(a,ctx,rows);one=bank.select([lookup[62502]])
    yy=a['measured'][rows]-a['correction'][rows];best=None
    for shift in np.linspace(-20,20,801):
        pred,vis,_,_=predict_orbits(one,obs,prior,v[:2],np.array([shift]),derivatives=False)
        r=circular(yy-pred[:,0]);score=np.sum((r/125)**2)+(shift/2)**2
        if vis.all() and (best is None or score<best['score']):
            best=dict(score=float(score),timing_s=float(shift),track_rms_hz=float(np.sqrt(np.mean(r*r))))
    trials=[]
    for label,shift in [('baseline',tau[nums.index(62502)]),('retime_62502',best['timing_s'])]:
        target=tau.copy();target[nums.index(62502)]=shift
        vv=v.copy();vv[7]=target.mean();vv[8:]=model.basis.T@(target-vv[7])
        np.testing.assert_allclose(vv[7]+model.basis@vv[8:],target,atol=1e-12,rtol=0)
        ev=model.evaluate_joint(vv,n);terms=ev[3];k=terms.responsibilities.argmax(axis=1)
        assoc=terms.responsibilities[np.arange(len(k)),k]>terms.clutter_probability
        trials.append(dict(label=label,timing_s=float(shift),objective=float(ev[0]),NLL=float(terms.nll),
            associated=int(assoc.sum()),target_track_associated=int(assoc[rows].sum()),
            target_track_associated_to_62502=int(np.sum(assoc[rows]&(np.array(nums)[k[rows]]==62502)))))
    result=dict(best_target_timing_only=best,trials=trials,
        qualification='Target-informed timing edit under the complete original scan objective. All '
        'other satellite timings and all receiver parameters remain fixed. No accepted optimized '
        'endpoint or held-out recovery claim.')
    (ROOT/'retime-control.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
