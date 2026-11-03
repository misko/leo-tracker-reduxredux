"""Common training-only timing union, re-evaluated under each RF arm.

Feasible tracklet selection is a baseline. Held-out global finite-set likelihood
is separate from decoding and does not yet model learned RX/channel activity.
"""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from adaptive_discovery import coherent_segments
from feasible_tracklets import select


def union_modes(discoveries):
    rows=discoveries[0]['original_rows'];modes={}
    for d in discoveries:
        if d['original_rows']!=rows:raise ValueError('RF discovery arms have different training rows')
        for p in d['proposals']:
            key=(p['catalog_number'],float(p['total_timing_s']))
            modes.setdefault(key,{k:p[k] for k in ('catalog_number','satellite_index','total_timing_s')})
    return [modes[k] for k in sorted(modes)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True);args=parser.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual,prepare_finite_set_likelihood
    sources=[ROOT/'training-discovery'/f'fold-{args.fold}'/arm/f'{args.scan}-proposals.json' for arm in ('fitted-c','zero-c')]
    discoveries=[json.loads(p.read_text()) for p in sources];modes=union_modes(discoveries)
    data=load_expanded_scan(SESSIONS[args.scan]);calibration_path=ROOT/'training-calibration'/f'fold-{args.fold}'/f'{args.scan}.json'
    calibration=json.loads(calibration_path.read_text())
    assert all(d['source_sha256']==digest(calibration_path) for d in discoveries)
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    training=training_view(data,train&canonical);testing=training_view(data,test&canonical)
    np.testing.assert_array_equal(training.original_rows,discoveries[0]['original_rows'])
    _,features=rf_features(training.rf,training.receiver,False);_,test_features=rf_features(testing.rf,testing.receiver,False)
    assert set(np.unique(training.rf))==set(np.unique(testing.rf))
    prepared=prepare_finite_set_likelihood(testing.measured,testing.group)
    output=ROOT/'training-union'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    arms={};pdet=.8/(13 if args.scan=='A' else 15)
    for arm,discovery in zip(('fitted-c','zero-c'),discoveries):
        params=np.array(calibration['arms'][arm]['parameters']);coeff=np.array(calibration['arms'][arm]['rf_coefficient_hz_per_ghz'])
        correction=features@coeff;proposals=[]
        for mode in modes:
            index=mode['satellite_index'];params[6+index]=mode['total_timing_s']
            predicted,visible,_=SharedPredictionPlan(training,[index]).predict(params)
            residual=circular_residual(training.measured,predicted+correction,ALIAS_HZ)
            good=np.flatnonzero(visible&(np.abs(residual)<=600))
            segments=coherent_segments(good,training.times,training.group,training.receiver,training.channel,residual)
            for s in segments:
                eligible=good[(training.receiver[good]==s['receiver'])&(training.channel[good]==s['channel'])
                    &(training.times[good]>=s['start_s']-1e-7)&(training.times[good]<=s['end_s']+1e-7)]
                s['eligible_rows']=eligible.tolist();s['eligible_residual_native_hz']=residual[eligible].tolist()
            proposals.append({**mode,'offset_s':mode['total_timing_s']-discovery['common_timing_s'],'segments':segments})
        selected=select(proposals,training.group,training.times,pdet)
        chosen=[proposals[pi] for pi in selected['selected_modes'].values()]
        indices=np.array([p['satellite_index'] for p in chosen],int)
        for p in chosen:params[6+p['satellite_index']]=p['total_timing_s']
        pred,vis,_=SharedPredictionPlan(testing,indices).predict(params)
        pred=pred.reshape(len(testing.times),-1)+(test_features@coeff)[:,None]
        ll=float(prepared.evaluate(pred,vis.reshape(pred.shape),sigma_hz=200.,detection_probability=pdet,
            clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
        arm_result=dict(training_assignments=selected['assignments'],chosen_modes=chosen,parameters=params.tolist(),
            coefficient=coeff.tolist(),train_assigned=len(selected['assignments']),train_denominator=len(training.times),
            selected_catalogs=len(chosen),heldout_global_log_likelihood=ll,
            heldout_gain_vs_clutter=ll-calibration['clutter_heldout_log_likelihood'],
            heldout_gain_vs_bootstrap_bank=ll-calibration['arms'][arm]['heldout_log_likelihood'],
            proposals_with_coherent_support=sum(bool(p['segments']) for p in proposals))
        arms[arm]=arm_result
        print(args.scan,arm,json.dumps({k:v for k,v in arm_result.items() if k not in ('training_assignments','chosen_modes','parameters')}),flush=True)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,union_modes=len(modes),
        union_catalogs=len({p['catalog_number'] for p in modes}),arms=arms,
        original_train_rows=training.original_rows.tolist(),original_test_rows=testing.original_rows.tolist(),
        source_sha256={str(p):digest(p) for p in [*sources,calibration_path]},elapsed_s=time.monotonic()-started,
        limitations=['No nuisance refit after expanded selection; calibration remains from the training bootstrap bank.',
            'Some calibration fits unconverged; status is recorded in source receipts.',
            'Training assignments are raw, without identity or negative-control gates; not defensible coverage.',
            'Held-out score assumes globally available satellites, not interval-specific activity; no test decoding.'])
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
