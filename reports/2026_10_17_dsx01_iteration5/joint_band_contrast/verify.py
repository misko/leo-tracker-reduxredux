"""Read-only terminal/prediction replay, separately costed from TRAIN fitting."""
from dataclasses import replace
import json
import numpy as np
from numpy.testing import assert_array_equal,assert_allclose
from run import HERE,ATTEMPT,PROFILE,BLOCKED,CONTROL,DATA,digest,read,save,verify_manifest
from run import load_training_context,predict_original,endpoint_status,density,PositionObservations
from model import free_context,predict_joint


def verify():
    for path,sha in read(HERE/'protocol.json')['source_sha256'].items():assert digest(path)==sha,path
    for filename,field in [('endpoint-freeze.json','endpoints'),('prediction-freeze.json','predictions')]:
        frozen=read(HERE/filename)
        for key,sha in frozen[field].items():
            prefix='fit' if field=='endpoints' else 'predictions';suffix='json' if field=='endpoints' else 'npz'
            assert digest(HERE/f'{prefix}-{key}.{suffix}')==sha
    counts={str(root):verify_manifest(root) for root in [BLOCKED,PROFILE]}
    context=load_training_context();source=read(ATTEMPT/'derivation.json')['source_id']
    rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']==source]
    obs=PositionObservations(tuple(r['observation_id'] for r in rows),np.array([r['time_s'] for r in rows]),
        np.array([r['measured_cfo_hz'] for r in rows]),np.array([r['actual_rf_hz'] for r in rows]),
        np.array([r['receiver']-1 for r in rows]),np.array([r['channel'] for r in rows]),np.ones(len(rows)))
    changed=replace(obs,measured_hz=obs.measured_hz+123456.789)
    endpoints={};exact_nesting={};prediction_error={}
    for arm in ['fitted-c','zero-c']:
        v=context.vector.copy()
        if arm=='zero-c':v[6]=0.
        ctx=replace(context,vector=v,fixed_c=arm=='zero-c')
        free=free_context(ctx)
        a=ctx.model.evaluate_joint(v,ctx.nuisance);b=free.model.evaluate_joint(v,free.nuisance)
        assert a[0]==b[0] and a[3].nll==b[3].nll
        assert_array_equal(a[1],b[1]);assert_array_equal(a[2],b[2][:-free.model.band_count])
        exact_nesting[arm]=dict(objective=a[0],physical_and_existing_nuisance_gradients_byte_exact=True)
        for method in ['frozen','free']:
            fit=read(HERE/f'fit-{method}-{arm}.json');v=np.array(fit['vector']);n=np.array(fit['nuisance'])
            target=free if method=='free' else ctx
            audit=endpoint_status(target,v,n);assert audit['accepted'] and audit['feasible']
            assert_allclose(audit['training_objective'],fit['diagnostics']['objective'],atol=1e-9,rtol=0)
            assert_allclose(audit['training_nll'],fit['diagnostics']['likelihood_nll'],atol=1e-9,rtol=0)
            assert_allclose(audit['stationarity'],fit['diagnostics']['stationarity'],atol=1e-9,rtol=0)
            adapter=predict_joint if method=='free' else predict_original
            p=adapter(target,v,n,obs);p_changed=adapter(target,v,n,changed)
            for name in p:assert_array_equal(p[name],p_changed[name])
            error=0.
            with np.load(HERE/f'predictions-{method}-{arm}.npz') as saved:
                for name in p:
                    assert_allclose(p[name],saved[name],atol=1e-9,rtol=0)
                    error=max(error,float(np.max(abs(p[name]-saved[name]),initial=0)))
            terms,details=density(obs.measured_hz,p['prediction_hz'],p['visibility_weight'],np.full(len(rows),125.),p['detection_probability'],ctx.model.score)
            best=terms.responsibilities.argmax(1);assigned=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
            with np.load(HERE/f'evaluation-{method}-{arm}.npz') as saved:
                assert_array_equal(saved['associated'],assigned)
                assert_array_equal(saved['best_number'],ctx.bank.numbers[best])
                assert_allclose(saved['row_nll'],details['row_nll'],atol=1e-9,rtol=0)
                assert_allclose(saved['residual_hz'],terms.residual_hz[np.arange(len(best)),best],atol=1e-9,rtol=0)
            key=f'{method}-{arm}';endpoints[key]=audit;prediction_error[key]=error
    save(HERE/'verification.json',dict(passed=True,source_hashes_unchanged=True,sealed_files_verified=counts,
        real_original_contrasts_exact_nesting=exact_nesting,endpoints=endpoints,
        metadata_prediction_max_error_hz=prediction_error,metadata_cfo_invariance=True,
        exact_saved_classification_replay=True,separate_verification_objective_calls=8,
        separate_verification_density_calls=4,separate_metadata_prediction_orbit_queries=8,
        selection_or_new_fits=False))
    print('PASS: four strict endpoints, exact real nesting/all gradients, CFO-blind transport, exact saved scoring')


if __name__=='__main__':verify()
