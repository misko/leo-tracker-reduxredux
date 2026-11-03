"""Fixed-training-parameter decoding comparison; NOT predictive likelihood.

Decoders inspect training and held-out peaks together to infer activity and
assignments, with embargo rows absent. Candidate identities, timings and RX/RF
calibration are learned from training only. Count only held-out assignments.
"""
import argparse,importlib.util,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from adaptive_discovery import coherent_segments
from compare_decoders import coherence_filter
from feasible_tracklets import select
from sparse_activity import decode


def checked_test_pairs(pairs,groups,test_mask):
    if len(pairs)!=len({r for r,c in pairs}):raise ValueError('Peak assigned twice')
    if len(pairs)!=len({(int(groups[r]),c) for r,c in pairs}):raise ValueError('Satellite assigned twice in a probe')
    return [(r,c) for r,c in pairs if test_mask[r]]


def load_history():
    # The numerical modules and the old prototype can both use a module named
    # common. Keep this report-local import from changing another module's port.
    previous=sys.modules.pop('common',None);sys.path.insert(0,str(OLD))
    spec=importlib.util.spec_from_file_location('heldout_history',OLD/'history/mht.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    try:spec.loader.exec_module(module)
    finally:
        sys.path.pop(0);sys.modules.pop('common',None)
        if previous is not None:sys.modules['common']=previous
    return module


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True);args=parser.parse_args();started=time.monotonic()
    history=load_history();sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual
    source=ROOT/'training-union'/f'fold-{args.fold}'/f'{args.scan}.json';receipt=json.loads(source.read_text())
    output=ROOT/'heldout-decoding'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    data=load_expanded_scan(SESSIONS[args.scan])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    np.testing.assert_array_equal(np.flatnonzero(train&canonical),receipt['original_train_rows'])
    np.testing.assert_array_equal(np.flatnonzero(test&canonical),receipt['original_test_rows'])
    d=training_view(data,(train|test)&canonical);is_test=test[d.original_rows]
    _,features=rf_features(d.rf,d.receiver,False);pdet=.8/(13 if args.scan=='A' else 15);arms={}
    for arm in ('fitted-c','zero-c'):
        baseline=receipt['arms'][arm];chosen=baseline['chosen_modes']
        indices=np.array([p['satellite_index'] for p in chosen]);numbers=np.array([p['catalog_number'] for p in chosen])
        params=np.array(baseline['parameters']);coeff=np.array(baseline['coefficient'])
        pred,vis,_=SharedPredictionPlan(d,indices).predict(params)
        pred=pred.reshape(len(d.times),-1)+(features@coeff)[:,None];vis=vis.reshape(pred.shape)
        residual=circular_residual(d.measured[:,None],pred,ALIAS_HZ)
        gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(residual/200)**2-np.log(2/ALIAS_HZ)
        gain[~vis|(np.abs(residual)>600)]=-np.inf
        methods={}
        for method in ('activity','history','tracklet'):
            t0=time.monotonic()
            if method=='activity':pairs=decode(d.times,d.group,d.receiver,d.channel,gain,vis,pdet,beam_width=16)
            elif method=='history':
                histories,_=history.track(d.times,d.group,residual,gain,lanes=4*d.receiver+d.channel-1,
                    beam=16,group_cap=16,top_per_row=3,state=True)
                pairs=[(r,c) for group in histories[0].assignments for r,c in group if c>=0]
            else:
                proposals=[]
                for col,p in enumerate(chosen):
                    good=np.flatnonzero(np.isfinite(gain[:,col]))
                    segments=coherent_segments(good,d.times,d.group,d.receiver,d.channel,residual[:,col])
                    for s in segments:
                        rr=good[(d.receiver[good]==s['receiver'])&(d.channel[good]==s['channel'])
                            &(d.times[good]>=s['start_s']-1e-7)&(d.times[good]<=s['end_s']+1e-7)]
                        s['eligible_rows']=rr.tolist();s['eligible_residual_native_hz']=residual[rr,col].tolist()
                    proposals.append({**p,'segments':segments})
                selected=select(proposals,d.group,d.times,pdet);lookup={int(n):i for i,n in enumerate(numbers)}
                pairs=[(r['row_index'],lookup[r['catalog_number']]) for r in selected['assignments']]
            seconds=time.monotonic()-t0
            raw=checked_test_pairs(pairs,d.group,is_test)
            assert all(np.isfinite(gain[r,c]) for r,c in pairs)
            coherent,_=coherence_filter(pairs,d.times,d.receiver,d.channel)
            retained=checked_test_pairs(coherent,d.group,is_test)
            e=np.array([residual[r,c] for r,c in retained])
            methods[method]=dict(raw_test_assigned=len(raw),coherent_test_assigned=len(retained),
                test_denominator=int(is_test.sum()),coherent_test_coverage=len(retained)/is_test.sum(),
                coherent_native_rms_hz=float(np.sqrt(np.mean(e**2))) if len(e) else None,decoding_s=seconds,
                assignments=[dict(row_index=int(d.original_rows[r]),catalog_number=int(numbers[c]),
                    residual_native_hz=float(residual[r,c])) for r,c in retained])
            print(args.scan,args.fold,arm,method,json.dumps({k:v for k,v in methods[method].items() if k!='assignments'}),flush=True)
        arms[arm]=dict(catalog_numbers=numbers.tolist(),methods=methods)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,arms=arms,original_test_rows=d.original_rows[is_test].tolist(),
        source_sha256=digest(source),elapsed_s=time.monotonic()-started,
        limitations=['Shared candidate/timing preprocessing uses the training tracklet selector and may favor that family.',
            'Held-out peaks are used for decoding/coherence, never parameter fitting or candidate discovery.',
            'Identity ambiguity, negative controls and additional scans are not validated here.',
            'Not strict predictive likelihood and not defensible assigned coverage.'])
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
