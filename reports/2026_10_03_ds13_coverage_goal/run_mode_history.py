"""Independent history timing selection on training only, with frozen test decoding."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from training_union import union_modes
from adaptive_discovery import coherent_segments
from compare_decoders import coherence_filter
from heldout_decoders import load_history,checked_test_pairs
from mode_history import track,rank_modes


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True)
    p.add_argument('--fold',type=int,choices=range(5),required=True)
    p.add_argument('--selection',choices=['joint-beam','lane-history'],default='joint-beam');args=p.parse_args()
    started=time.monotonic();old_history=load_history();sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual,prepare_finite_set_likelihood
    sources=[ROOT/'training-discovery'/f'fold-{args.fold}'/arm/f'{args.scan}-proposals.json' for arm in ('fitted-c','zero-c')]
    discoveries=[json.loads(s.read_text()) for s in sources];modes=union_modes(discoveries)
    calibration_path=ROOT/'training-calibration'/f'fold-{args.fold}'/f'{args.scan}.json'
    calibration=json.loads(calibration_path.read_text())
    assert all(d['source_sha256']==digest(calibration_path) for d in discoveries)
    folder='independent-history' if args.selection=='joint-beam' else 'independent-lane-history'
    target=ROOT/folder/f'fold-{args.fold}'/f'{args.scan}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise FileExistsError(target)
    data=load_expanded_scan(SESSIONS[args.scan])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    d=training_view(data,canonical&train);e=training_view(data,canonical&(train|test));testing=training_view(data,canonical&test)
    np.testing.assert_array_equal(d.original_rows,discoveries[0]['original_rows'])
    _,features=rf_features(d.rf,d.receiver,False);_,ef=rf_features(e.rf,e.receiver,False);_,tf=rf_features(testing.rf,testing.receiver,False)
    assert set(np.unique(d.rf))==set(np.unique(e.rf))==set(np.unique(testing.rf))
    prepared=prepare_finite_set_likelihood(testing.measured,testing.group)
    pdet=.8/(13 if args.scan=='A' else 15);constant=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-np.log(2/ALIAS_HZ)
    arms={}
    for arm,discovery in zip(('fitted-c','zero-c'),discoveries):
        t0=time.monotonic();params=np.array(calibration['arms'][arm]['parameters']);coeff=np.array(calibration['arms'][arm]['rf_coefficient_hz_per_ghz'])
        residual=np.zeros((len(d.times),len(modes)));gain=np.full_like(residual,-np.inf)
        for col,m in enumerate(modes):
            params[6+m['satellite_index']]=m['total_timing_s']
            pred,vis,_=SharedPredictionPlan(d,[m['satellite_index']]).predict(params)
            r=circular_residual(d.measured,pred+features@coeff,ALIAS_HZ);residual[:,col]=r
            good=np.flatnonzero(vis&(np.abs(r)<=600))
            segments=coherent_segments(good,d.times,d.group,d.receiver,d.channel,r)
            for s in segments:
                rows=good[(d.receiver[good]==s['receiver'])&(d.channel[good]==s['channel'])&(d.times[good]>=s['start_s']-1e-7)&(d.times[good]<=s['end_s']+1e-7)]
                gain[rows,col]=constant-.5*(r[rows]/200)**2
        numbers=np.array([m['catalog_number'] for m in modes]);offsets=np.array([m['total_timing_s']-discovery['common_timing_s'] for m in modes])
        if args.selection=='joint-beam':
            h=track(d.times,d.group,4*d.receiver+d.channel-1,residual,gain,numbers,offsets)
            training_pairs=h.pairs;training_score=h.score
        else:
            choices,scores,training_pairs=rank_modes(d.times,d.group,4*d.receiver+d.channel-1,residual,gain,numbers,offsets)
            training_score=float(sum(scores[c] for c in choices.values()))
        coherent,_=coherence_filter(training_pairs,d.times,d.receiver,d.channel)
        cols=sorted({c for _,c in coherent});chosen=[modes[c] for c in cols]
        for m in chosen:params[6+m['satellite_index']]=m['total_timing_s']
        indices=np.array([m['satellite_index'] for m in chosen],int)
        pred,vis,_=SharedPredictionPlan(testing,indices).predict(params)
        pred=pred.reshape(len(testing.times),len(indices))+(tf@coeff)[:,None]
        ll=float(prepared.evaluate(pred,vis.reshape(pred.shape),sigma_hz=200.,detection_probability=pdet,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
        pred,vis,_=SharedPredictionPlan(e,indices).predict(params)
        pred=pred.reshape(len(e.times),len(indices))+(ef@coeff)[:,None];vis=vis.reshape(pred.shape)
        r=circular_residual(e.measured[:,None],pred,ALIAS_HZ);g=constant-.5*(r/200)**2;g[~vis|(np.abs(r)>600)]=-np.inf
        if len(indices):
            hs,_=old_history.track(e.times,e.group,r,g,lanes=4*e.receiver+e.channel-1,beam=16,group_cap=16,top_per_row=3,state=True)
            pairs=[(row,col) for group in hs[0].assignments for row,col in group if col>=0]
        else:pairs=[]
        kept,_=coherence_filter(pairs,e.times,e.receiver,e.channel)
        kept=checked_test_pairs(kept,e.group,test[e.original_rows])
        records=[dict(row_index=int(e.original_rows[row]),catalog_number=chosen[col]['catalog_number'],residual_native_hz=float(r[row,col])) for row,col in kept]
        arms[arm]=dict(training_provisional_edges=len(training_pairs),training_coherent_provisional_edges=len(coherent),chosen_modes=chosen,
            heuristic_training_score=training_score,test_denominator=len(testing.times),coherent_test_assigned=len(kept),coherent_test_coverage=len(kept)/len(testing.times),
            coherent_native_rms_hz=float(np.sqrt(np.mean([r[row,col]**2 for row,col in kept]))) if kept else None,
            heldout_gain_vs_clutter=ll-calibration['clutter_heldout_log_likelihood'],assignments=records,elapsed_s=time.monotonic()-t0)
        print(args.scan,args.fold,arm,json.dumps({k:v for k,v in arms[arm].items() if k not in ('assignments','chosen_modes')}),flush=True)
    result=dict(scope=__doc__,selection=args.selection,scan=args.scan,fold=args.fold,training_union_modes=len(modes),arms=arms,
        original_train_rows=d.original_rows.tolist(),original_test_rows=testing.original_rows.tolist(),
        sources={str(s):digest(s) for s in [*sources,calibration_path,ROOT/'mode_history.py',ROOT/'run_mode_history.py']},elapsed_s=time.monotonic()-started,
        limitations=['Bounded beam can prematurely commit to early timing evidence; not exhaustive global optimization.',
            'Timing candidates and choice use training only; test decoding uses evaluation peaks for assignments/coherence.',
            'OU states affect assignment scores only; reported residuals and strict predictive likelihood use unmodified physical curves.',
            'No new identity or negative-control certification; coverage is not defensible goal coverage.',
            'Existing calibration convergence limitations still apply.'])
    if args.selection=='lane-history':result['limitations'].append('Per-catalog training histories may reuse peaks during candidate ranking; these are provisional edges, not coverage. Only final joint decoding enforces exclusive assignments.')
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
