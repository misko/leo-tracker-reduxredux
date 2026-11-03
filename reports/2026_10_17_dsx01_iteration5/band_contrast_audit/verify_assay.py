"""No-fit replay of exact changed-contrast models and frozen evaluation arrays."""
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import numpy as np
from numpy.testing import assert_array_equal,assert_allclose
from run_assay import HERE,BLOCKED,DATA,digest
sys.path.append(str(BLOCKED))
from training_context import load_training_context,predict_original
from leo.analysis.sequential_group_calibration import SequentialShift,fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective,density
from leo.contracts.regional_position import PositionObservations


def run():
    protocol=json.loads((HERE/'protocol.json').read_text());results=json.loads((HERE/'results.json').read_text())
    freeze=json.loads((HERE/'prediction-freeze.json').read_text())
    for name,sha in protocol['research_code_sha256'].items():assert digest(HERE/name)==sha
    assert digest(BLOCKED/'manifest.json')==protocol['source_blocked_manifest_sha256']
    ctx=load_training_context();seedv=ctx.vector.copy();seedn=ctx.nuisance.copy()
    rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']=='S03']
    obs=PositionObservations(tuple(r['observation_id'] for r in rows),np.array([r['time_s'] for r in rows]),
        np.zeros(len(rows)),np.array([r['actual_rf_hz'] for r in rows]),np.array([r['receiver']-1 for r in rows]),np.array([r['channel'] for r in rows]),np.ones(len(rows)))
    measured=np.array([r['measured_cfo_hz'] for r in rows]);evidence=[]
    for arm in ['fitted-c','zero-c']:
        selection=json.loads((HERE/f'selection-{arm}.json').read_text())
        assert digest(HERE/f'selection-{arm}.json')==freeze['selections'][arm]
        assert digest(HERE/f'predictions-{arm}.npz')==freeze['predictions'][arm]
        v,n=np.array(selection['vector']),np.array(selection['nuisance']);expectedv=seedv.copy()
        if arm=='zero-c':expectedv[6]=0
        assert_array_equal(v,expectedv);assert_array_equal(n,seedn)
        diag=selection['diagnostics'];assert diag['evaluations']==diag['full_shared_objective_calls']+diag['partial_or_full_density_calls']<=200
        assert diag['partial_or_full_density_calls']==diag['profile_requests']-diag['cache_hits']+2
        assert diag['elapsed_seconds']<=120.1
        old=SequentialShift((0,1),selection['original_offsets_hz']);new=SequentialShift((0,1),selection['absolute_offsets_hz'])
        common=copy(ctx.model.original.base);train=ctx.observations
        common.baseline=common.baseline-old.predict(train.receiver,train.channel>=5)
        model=SharedScanObjective(fixed_shift_objective(common,new),new)
        for key in ['baseline','profile']:
            current=ctx.model if key=='baseline' else model
            ev=current.evaluate_joint(v,n)
            savedJ=selection['training_objective_before' if key=='baseline' else 'training_objective']
            savedN=selection['training_nll_before' if key=='baseline' else 'training_nll']
            assert_allclose(ev[0],savedJ,atol=1e-8,rtol=0);assert_allclose(ev[3].nll,savedN,atol=1e-8,rtol=0)
            pred=predict_original(replace(ctx,model=current,full_model=current),v,n,obs)
            with np.load(HERE/f'predictions-{arm}.npz') as frozen:
                assert_allclose(pred['prediction_hz'],frozen[key+'_prediction_hz'],atol=3e-10,rtol=0)
                assert_array_equal(pred['visibility_weight'],frozen['visibility_weight'])
                assert_array_equal(pred['detection_probability'],frozen['detection_probability'])
                trainmask=frozen['train_mask'];heldmask=frozen['held_mask']
            terms,details=density(measured,pred['prediction_hz'],pred['visibility_weight'],np.full(len(rows),125.),pred['detection_probability'],current.score)
            best=terms.responsibilities.argmax(1);assigned=terms.responsibilities[np.arange(len(rows)),best]>terms.clutter_probability
            with np.load(HERE/f'evaluation-{arm}.npz') as frozen:
                assert_array_equal(assigned,frozen[key+'_associated'])
                assert_allclose(terms.residual_hz[np.arange(len(rows)),best],frozen[key+'_residual_hz'],atol=3e-10,rtol=0)
            record=next(r for r in results['results'] if r['arm']==arm and r['method']==key)
            assert int(assigned[heldmask].sum())==record['held']['associated']
            assert_allclose(details['row_nll'][heldmask].sum(),record['held']['frequency_nll'],atol=1e-8,rtol=0)
        evidence.append(dict(arm=arm,profile_evaluations=diag['evaluations'],
            direct_shared_objective_prior_and_nll_match=True,full_frozen_prediction_and_classifier_replay=True,
            selection_fixed_all_noncontrast_coordinates=True))
    assert_array_equal(ctx.vector,seedv);assert_array_equal(ctx.nuisance,seedn)
    report=dict(passed=True,evidence=evidence,
        replay_calls=dict(context_strict_shared_objective=1,direct_shared_objective=4,
            metadata_prediction_orbit_queries=4,evaluation_density=4),
        initial_context_replay_shared_objective_calls=1,
        qualification='Read-only verification, no refit or selection. Replay calls are reported separately from the318 profile calls and4 initial scoring density calls.')
    with (HERE/'verification.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':run()
