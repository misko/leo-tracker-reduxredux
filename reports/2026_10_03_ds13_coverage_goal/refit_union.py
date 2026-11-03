"""Old+rediscovered training timing union under refitted calibration, fold zero."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from training_union import union_modes
from adaptive_discovery import coherent_segments
from feasible_tracklets import select


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);args=p.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual,prepare_finite_set_likelihood
    arms=('fitted-c','zero-c');oldpaths=[ROOT/'training-discovery/fold-0'/a/f'{args.scan}-proposals.json' for a in arms]
    newpaths=[ROOT/'refit-rediscovery'/a/'training-discovery/fold-0'/a/f'{args.scan}-proposals.json' for a in arms]
    discoveries=[json.loads(p.read_text()) for p in oldpaths+newpaths];modes=union_modes(discoveries)
    for arm,d in zip(arms,discoveries[2:]):
        source=ROOT/'refit-rediscovery'/arm/'training-calibration/fold-0'/f'{args.scan}.json'
        assert d['source_sha256']==digest(source)
    rp=ROOT/'expanded-training-refit/fold-0'/f'{args.scan}.json';refit=json.loads(rp.read_text())
    old=json.loads((ROOT/'training-union/fold-0'/f'{args.scan}.json').read_text())
    data=load_expanded_scan(SESSIONS[args.scan])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],0);canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    d=training_view(data,train&canonical);t=training_view(data,test&canonical)
    np.testing.assert_array_equal(d.original_rows,discoveries[0]['original_rows']);np.testing.assert_array_equal(t.original_rows,refit['original_test_rows'])
    _,features=rf_features(d.rf,d.receiver,False);_,tf=rf_features(t.rf,t.receiver,False)
    prepared=prepare_finite_set_likelihood(t.measured,t.group);pdet=.8/(13 if args.scan=='A' else 15)
    empty=np.empty((len(t.times),0));clutter=float(prepared.evaluate(empty,empty.astype(bool),sigma_hz=200.,detection_probability=pdet,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
    output=ROOT/'refit-discovery-evaluation';output.mkdir(exist_ok=True)
    frozen=output/'frozen'
    if not frozen.exists():
        try:frozen.symlink_to(ROOT/'frozen',target_is_directory=True)
        except FileExistsError:pass
    if frozen.resolve()!=(ROOT/'frozen').resolve():raise ValueError('Unexpected frozen data')
    target=output/'training-union/fold-0'/f'{args.scan}.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise FileExistsError(target)
    results={}
    for arm,discovery in zip(arms,discoveries[2:]):
        fit=refit['arms'][arm];params=np.array(fit['parameters']);coeff=np.array(fit['coefficient']);proposals=[]
        for m in modes:
            params[6+m['satellite_index']]=m['total_timing_s'];pred,vis,_=SharedPredictionPlan(d,[m['satellite_index']]).predict(params)
            residual=circular_residual(d.measured,pred+features@coeff,ALIAS_HZ);good=np.flatnonzero(vis&(abs(residual)<=600))
            segments=coherent_segments(good,d.times,d.group,d.receiver,d.channel,residual)
            for s in segments:
                rr=good[(d.receiver[good]==s['receiver'])&(d.channel[good]==s['channel'])&(d.times[good]>=s['start_s']-1e-7)&(d.times[good]<=s['end_s']+1e-7)]
                s['eligible_rows']=rr.tolist();s['eligible_residual_native_hz']=residual[rr].tolist()
            proposals.append({**m,'offset_s':m['total_timing_s']-discovery['common_timing_s'],'segments':segments})
        selected=select(proposals,d.group,d.times,pdet);chosen=[proposals[pi] for pi in selected['selected_modes'].values()]
        for m in chosen:params[6+m['satellite_index']]=m['total_timing_s']
        indices=np.array([m['satellite_index'] for m in chosen],int);pred,vis,_=SharedPredictionPlan(t,indices).predict(params)
        pred=pred.reshape(len(t.times),len(indices))+(tf@coeff)[:,None]
        ll=float(prepared.evaluate(pred,vis.reshape(pred.shape),sigma_hz=200.,detection_probability=pdet,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
        results[arm]=dict(parameters=params.tolist(),coefficient=coeff.tolist(),chosen_modes=chosen,training_assignments=selected['assignments'],
            selected_catalogs=len(chosen),train_assigned=len(selected['assignments']),train_denominator=len(d.times),
            heldout_global_log_likelihood=ll,heldout_gain_vs_clutter=ll-clutter,heldout_change_vs_fixed_catalog_refit=ll-fit['heldout_log_likelihood'],
            heldout_change_vs_original=ll-old['arms'][arm]['heldout_global_log_likelihood'])
        print(args.scan,arm,json.dumps({k:v for k,v in results[arm].items() if k not in ('parameters','coefficient','chosen_modes','training_assignments')}),flush=True)
    target.write_text(json.dumps(dict(scope=__doc__,scan=args.scan,fold=0,arms=results,union_modes=len(modes),
        original_train_rows=d.original_rows.tolist(),original_test_rows=t.original_rows.tolist(),sources={str(p):digest(p) for p in oldpaths+newpaths+[rp]},
        elapsed_s=time.monotonic()-started,warning='Training selection and strict held-out likelihood only; no new identity or negative-control certification.'),indent=2))


if __name__=='__main__':main()
