"""Prune provisional catalogs lacking coherent exclusive training support."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from compare_decoders import coherence_filter
from heldout_decoders import load_history,checked_test_pairs


def prune(ncols,decode,coherent):
    active=list(range(ncols));trace=[]
    while active:
        pairs=decode(active)
        if len(pairs)!=len({r for r,c in pairs}):raise ValueError('Nonexclusive peak assignment')
        if any(c not in active for r,c in pairs):raise ValueError('Decoder returned inactive catalog')
        kept=coherent(pairs);supported={c for r,c in kept}
        if not supported.issubset(active):raise ValueError('Invalid coherent support')
        trace.append(dict(catalogs=len(active),coherent_catalogs=len(supported),coherent_peaks=len(kept)))
        if supported==set(active):return active,kept,trace
        active=[c for c in active if c in supported]
    return [],[],trace


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True);args=parser.parse_args()
    started=time.monotonic();history=load_history();sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual,prepare_finite_set_likelihood
    source=ROOT/'independent-lane-history/fold-0'/f'{args.scan}.json';prior=json.loads(source.read_text())
    cp=ROOT/'training-calibration/fold-0'/f'{args.scan}.json';cal=json.loads(cp.read_text())
    assert prior['sources'][str(cp)]==digest(cp)
    target=ROOT/'exclusive-history/fold-0'/f'{args.scan}.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise FileExistsError(target)
    data=load_expanded_scan(SESSIONS[args.scan])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],0);canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    d=training_view(data,canonical&train);e=training_view(data,canonical&(train|test));t=training_view(data,canonical&test)
    np.testing.assert_array_equal(d.original_rows,prior['original_train_rows']);np.testing.assert_array_equal(t.original_rows,prior['original_test_rows'])
    pdet=.8/(13 if args.scan=='A' else 15);constant=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-np.log(2/ALIAS_HZ)
    prepared=prepare_finite_set_likelihood(t.measured,t.group);arms={}
    for arm in ('fitted-c','zero-c'):
        chosen=prior['arms'][arm]['chosen_modes'];params=np.array(cal['arms'][arm]['parameters']);coeff=np.array(cal['arms'][arm]['rf_coefficient_hz_per_ghz'])
        for m in chosen:params[6+m['satellite_index']]=m['total_timing_s']
        indices=np.array([m['satellite_index'] for m in chosen],int)
        def arrays(view):
            _,features=rf_features(view.rf,view.receiver,False)
            pred,vis,_=SharedPredictionPlan(view,indices).predict(params)
            pred=pred.reshape(len(view.times),len(indices))+(features@coeff)[:,None];vis=vis.reshape(pred.shape)
            residual=circular_residual(view.measured[:,None],pred,ALIAS_HZ)
            gain=constant-.5*(residual/200)**2;gain[~vis|(np.abs(residual)>600)]=-np.inf
            return pred,vis,residual,gain
        _,_,r,g=arrays(d)
        def decode(active):
            hs,_=history.track(d.times,d.group,r[:,active],g[:,active],lanes=4*d.receiver+d.channel-1,beam=16,group_cap=16,top_per_row=3,state=True)
            pairs=[(row,active[c]) for group in hs[0].assignments for row,c in group if c>=0]
            checked_test_pairs(pairs,d.group,np.ones(len(d.times),bool))
            return pairs
        active,training,trace=prune(len(chosen),decode,lambda pairs:coherence_filter(pairs,d.times,d.receiver,d.channel)[0])
        pred,vis,_,_=arrays(t)
        ll=float(prepared.evaluate(pred[:,active],vis[:,active],sigma_hz=200.,detection_probability=pdet,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
        _,_,r,g=arrays(e)
        if active:
            hs,_=history.track(e.times,e.group,r[:,active],g[:,active],lanes=4*e.receiver+e.channel-1,beam=16,group_cap=16,top_per_row=3,state=True)
            pairs=[(row,active[c]) for group in hs[0].assignments for row,c in group if c>=0]
        else:pairs=[]
        kept,_=coherence_filter(pairs,e.times,e.receiver,e.channel);kept=checked_test_pairs(kept,e.group,test[e.original_rows])
        records=[dict(row_index=int(e.original_rows[row]),catalog_number=chosen[c]['catalog_number'],residual_native_hz=float(r[row,c])) for row,c in kept]
        arms[arm]=dict(initial_catalogs=len(chosen),selected_catalogs=len(active),trace=trace,chosen_modes=[chosen[c] for c in active],training_exclusive_coherent_peaks=len(training),
            coherent_test_assigned=len(kept),test_denominator=len(t.times),coherent_test_coverage=len(kept)/len(t.times),
            coherent_native_rms_hz=float(np.sqrt(np.mean([r[row,c]**2 for row,c in kept]))) if kept else None,
            heldout_gain_vs_clutter=ll-cal['clutter_heldout_log_likelihood'],assignments=records)
        print(args.scan,arm,json.dumps({k:v for k,v in arms[arm].items() if k not in ('assignments','chosen_modes')}),flush=True)
    target.write_text(json.dumps(dict(scope=__doc__,scan=args.scan,fold=0,arms=arms,original_test_rows=t.original_rows.tolist(),original_train_rows=d.original_rows.tolist(),
        sources={str(p):digest(p) for p in [source,cp,ROOT/'exclusive_history.py']},elapsed_s=time.monotonic()-started,
        limitations=['One development fold only; timing ranker unchanged; no refit.', 'Candidate pruning uses exclusive coherent training support only, never test outcomes.',
            'Coherent test decoding is not certified defensible coverage; identity and negative-control gates remain outstanding.',
            'Monotone pruning cannot recover a catalog rejected by earlier competition; no optimality claim.']),indent=2))


if __name__=='__main__':main()
