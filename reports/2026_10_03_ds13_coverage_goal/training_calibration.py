"""Matched training-only nuisance pilot; not the final decoder validation."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,digest,split_masks
from training_bootstrap import training_view
from coherent_bootstrap import wrap


def seed_catalogs(bootstrap):
    centers=[m[0]['offset_hz'] if m else None for m in bootstrap['modes']]
    return sorted({p['catalog_number'] for p in bootstrap['proposals']
                   if centers[p['receiver']] is not None and abs(wrap(p['offset_hz']-centers[p['receiver']]))<=2000})


def validate_resume(previous,scan,fold,numbers,source_sha256):
    if (previous['scan']!=scan or previous['fold']!=fold or
            previous['catalog_numbers']!=numbers or previous['source_sha256']!=source_sha256):
        raise ValueError('Resume provenance or candidate set changed')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import (load_expanded_scan,SharedPredictionPlan,prepare_finite_set_likelihood,
        rf_features,run_profile,ZeroRF,CalibrationObjective)
    data=load_expanded_scan(SESSIONS[args.scan]);source=ROOT/'training-coherent-bootstrap'/f'fold-{args.fold}'/f'{args.scan}.json'
    bootstrap=json.loads(source.read_text());numbers=seed_catalogs(bootstrap)
    if not numbers:raise RuntimeError('Bootstrap abstained: no supported seed identities to calibrate; do not manufacture an offset fit')
    output=ROOT/'training-calibration'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    previous_path=output/f'{args.scan}.json'
    target=output/f'{args.scan}-refined.json' if args.resume else previous_path
    if target.exists():raise FileExistsError(f'Preserve existing result: {target}')
    previous=json.loads(previous_path.read_text()) if args.resume else None
    if previous is not None:validate_resume(previous,args.scan,args.fold,numbers,digest(source))
    indices=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    training=training_view(data,train&canonical);testing=training_view(data,test&canonical)
    assert np.array_equal(training.original_rows,np.array(bootstrap['train_rows']))
    parameters=np.array(bootstrap['parameters']);pdet=.8/(13 if args.scan=='A' else 15)
    prepared=prepare_finite_set_likelihood(testing.measured,testing.group)
    # RF centering is a model convention fixed by the scan's channel metadata,
    # not by held-out measured frequencies. Both splits retain all four channels.
    _,features=rf_features(testing.rf,testing.receiver,False)
    assert set(np.unique(testing.rf))==set(np.unique(training.rf))
    def predictive(params,coeff):
        pred,visible,_=SharedPredictionPlan(testing,indices).predict(params)
        pred=pred.reshape(len(testing.times),-1)+(features@np.asarray(coeff))[:,None]
        return float(prepared.evaluate(pred,visible.reshape(pred.shape),sigma_hz=200.,
            detection_probability=pdet,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
    empty=np.empty((len(testing.times),0))
    clutter=float(prepared.evaluate(empty,empty.astype(bool),sigma_hz=200.,detection_probability=pdet,
        clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
    initial_ll=predictive(parameters,[0.]);arms={}
    for arm,factory in [('fitted-c',CalibrationObjective),('zero-c',ZeroRF)]:
        current=None;attempts=[]
        initial_parameters=parameters if previous is None else np.array(previous['arms'][arm]['parameters'])
        initial_coeff=[0.] if previous is None else previous['arms'][arm]['rf_coefficient_hz_per_ghz']
        for _ in range(4):
            fit=run_profile(training,initial_parameters,indices,initial_coeff,parameters[:2],probability_override=pdet,
                start_vector=current,budget_s=8.,objective_factory=factory)
            attempts.append({k:fit[k] for k in ('success','status','objective','projected_nuisance_gradient_inf_norm')})
            current=fit['vector']
            if fit['success']:break
        ll=predictive(fit['parameters'],fit['rf_coefficient_hz_per_ghz'])
        arms[arm]=dict(attempts=attempts,parameters=np.asarray(fit['parameters']).tolist(),
            rf_coefficient_hz_per_ghz=np.asarray(fit['rf_coefficient_hz_per_ghz']).tolist(),
            heldout_log_likelihood=ll,heldout_gain_vs_clutter=ll-clutter,heldout_gain_vs_initializer=ll-initial_ll)
        print(args.scan,arm,json.dumps({k:v for k,v in arms[arm].items() if k!='parameters'}),flush=True)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,catalog_numbers=numbers,train_rows=len(training.times),
        test_rows=len(testing.times),test_groups=len(np.unique(testing.group)),arms=arms,
        initializer_heldout_log_likelihood=initial_ll,clutter_heldout_log_likelihood=clutter,
        source_sha256=digest(source),elapsed_s=time.monotonic()-started,
        resumed_from_sha256=digest(previous_path) if previous is not None else None,
        limitations=['Single-fold pilot; not the requested full five-fold evaluation.',
            'Seed candidates from zero-timing coherent bootstrap; adaptive training timing discovery still required.',
            'Global observed-positive finite-set likelihood, not receiver/channel activity decoder prediction.',
            'No test-set decoding, no coverage claim, no negative-control pass.'])
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
