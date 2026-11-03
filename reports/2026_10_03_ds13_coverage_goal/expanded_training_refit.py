"""Training-only nuisance refit after union-based exclusive track selection."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,digest,split_masks
from training_bootstrap import training_view


def assert_row_lineage(training,testing,receipt):
    np.testing.assert_array_equal(training,receipt['original_train_rows'])
    np.testing.assert_array_equal(testing,receipt['original_test_rows'])
    if set(training)&set(testing):raise ValueError('Training/test leakage')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True);args=parser.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import (load_expanded_scan,SharedPredictionPlan,prepare_finite_set_likelihood,
        rf_features,run_profile,ZeroRF,CalibrationObjective)
    source=ROOT/'training-union'/f'fold-{args.fold}'/f'{args.scan}.json';receipt=json.loads(source.read_text())
    output=ROOT/'expanded-training-refit'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    data=load_expanded_scan(SESSIONS[args.scan])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    training=training_view(data,train&canonical);testing=training_view(data,test&canonical)
    assert_row_lineage(training.original_rows,testing.original_rows,receipt)
    _,features=rf_features(testing.rf,testing.receiver,False)
    assert set(np.unique(testing.rf))==set(np.unique(training.rf))
    prepared=prepare_finite_set_likelihood(testing.measured,testing.group);arms={}
    pdet=.8/(13 if args.scan=='A' else 15)
    empty=np.empty((len(testing.times),0))
    clutter=prepared.evaluate(empty,empty.astype(bool),sigma_hz=200.,detection_probability=pdet,
        clutter_rate=2.,return_gradient=False,return_precision=False)
    for arm,factory in [('fitted-c',CalibrationObjective),('zero-c',ZeroRF)]:
        selected=receipt['arms'][arm];indices=np.array([p['satellite_index'] for p in selected['chosen_modes']])
        params=np.array(selected['parameters']);coeff=selected['coefficient'];current=None;attempts=[]
        for _ in range(4):
            fit=run_profile(training,params,indices,coeff,params[:2],probability_override=pdet,
                start_vector=current,budget_s=8.,objective_factory=factory)
            current=fit['vector'];attempts.append({k:fit[k] for k in ('success','status','objective','projected_nuisance_gradient_inf_norm')})
            if fit['success']:break
        prediction,visible,_=SharedPredictionPlan(testing,indices).predict(fit['parameters'])
        prediction=prediction.reshape(len(testing.times),-1)+(features@np.array(fit['rf_coefficient_hz_per_ghz']))[:,None]
        scored=prepared.evaluate(prediction,visible.reshape(prediction.shape),sigma_hz=200.,detection_probability=pdet,
            clutter_rate=2.,return_gradient=False,return_precision=False)
        ll=float(scored['total_log_likelihood']);arms[arm]=dict(parameters=np.asarray(fit['parameters']).tolist(),
            coefficient=np.asarray(fit['rf_coefficient_hz_per_ghz']).tolist(),attempts=attempts,
            catalog_numbers=[p['catalog_number'] for p in selected['chosen_modes']],
            heldout_log_likelihood=ll,heldout_gain_vs_clutter=ll-clutter['total_log_likelihood'],
            heldout_change_after_refit=ll-selected['heldout_global_log_likelihood'],
            heldout_group_values=scored['group_values'].tolist(),
            heldout_group_gain_vs_clutter=(scored['log_likelihood']-clutter['log_likelihood']).tolist())
        print(args.scan,args.fold,arm,json.dumps({k:v for k,v in arms[arm].items() if k not in
            ('parameters','heldout_group_values','heldout_group_gain_vs_clutter','catalog_numbers')}),flush=True)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,arms=arms,source_sha256=digest(source),
        elapsed_s=time.monotonic()-started,original_train_rows=training.original_rows.tolist(),
        original_test_rows=testing.original_rows.tolist(),limitations=[
            'Same union candidate pool and fitting budgets, but each RF arm retains its own selected subset.',
            'Frozen selected identities; associations and activity must be revalidated after nuisance changes.',
            'Global positive-group predictive likelihood, not activity-aware decoder validation or coverage.'])
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
