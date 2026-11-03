"""Independent no-fit replay of saved pilot endpoints and actual singleton nesting."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
sys.path[:0]=[str(REPORTS/'2026_10_16_dsx01_models'),str(REPORTS/'2026_10_16_dsx01_iteration2')]
from common import load_context,endpoint_status,point_state,save_json
from bank_expansion import fixed_shift
from mixture_model import PeakMixtureObjective
from peak_data import all_peaks
from transport import transport
from run_pilot import digest


def main():
    import test_mixture
    tests=unittest.defaultTestLoader.loadTestsFromModule(test_mixture)
    result=unittest.TextTestRunner(verbosity=1).run(tests)
    if not result.wasSuccessful():raise AssertionError('Synthetic tests failed')
    records=[(p,json.loads(p.read_text())) for p in sorted((HERE/'results').glob('*.json'))]
    evidence=[]
    for sid in sorted(set(r['source_id'] for _,r in records)):
        original=load_context(sid);shift=fixed_shift(original.model)
        singleton=PeakMixtureObjective(original.model.original,shift,np.arange(len(original.observations.times_s)))
        a=original.model.evaluate_joint(original.vector,original.nuisance)
        b=singleton.evaluate_joint(original.vector,original.nuisance)
        assert a[0]==b[0];assert a[3].nll==b[3].nll
        assert_array_equal(a[1],b[1]);assert_array_equal(a[2],b[2])
        peaks,group,_=all_peaks(original,shift)
        assert peaks.model.score==original.model.score
        assert peaks.bank is original.bank and peaks.prior is original.prior
        assert len(peaks.model.initial_nuisance)==len(original.model.initial_nuisance)
        for name in ['clock_count','group_count','base_nuisance_count','size']:
            assert getattr(peaks.model,name)==getattr(original.model,name)
        for name in ['group_limits','group_scales','observation_precision']:
            assert_array_equal(getattr(peaks.model,name),getattr(original.model,name))
        assert_array_equal(peaks.model.original.base.precision,original.model.original.base.precision)
        assert_array_equal(peaks.model.original.baseline,
            shift.predict(peaks.observations.receiver,peaks.observations.channel>=5))
        for path,r in records:
            if r['source_id']!=sid:continue
            for name,sha in r['code_sha256'].items():assert digest(HERE/name)==sha
            for name,sha in r['upstream_code_sha256'].items():assert digest(Path(name))==sha
            assert digest(Path(r['seed']['path']))==r['seed']['sha256']
            ov,on=np.asarray(r['vector']),np.asarray(r['nuisance'])
            mv,mn=np.asarray(r['mixture_vector']),np.asarray(r['mixture_nuisance'])
            back,bn,closure=transport(peaks.model,original.model,mv,mn,shift)
            assert_allclose(back,ov,atol=1e-9,rtol=0);assert_array_equal(bn,on)
            oe,od,best,assigned,residual=point_state(original.model,ov,on)
            me,details=peaks.model.evaluate_details(mv,mn)
            assert od['prior_penalty']==details['prior_penalty']
            fit_context=peaks if r['method']=='mixture-continuation' else original
            fv,fn=(mv,mn) if r['method']=='mixture-continuation' else (ov,on)
            audit=endpoint_status(replace(fit_context,fixed_c=r['arm']=='zero-c'),fv,fn)
            assert audit['accepted']==r['audit']['accepted']
            assert_allclose(audit['stationarity'],r['audit']['stationarity'],atol=1e-10,rtol=1e-8)
            for actual,saved in [(oe[0],r['winner_full_scan']['objective']),
                (oe[3].nll,r['winner_full_scan']['likelihood_nll']),
                (me[0],r['mixture_group']['objective']),
                (me[3].nll,r['mixture_group']['likelihood_nll'])]:
                assert_allclose(actual,saved,atol=1e-8,rtol=0)
            fitted=me if r['method']=='mixture-continuation' else oe
            assert_allclose(fitted[0],r['diagnostics']['objective'],atol=1e-8,rtol=0)
            assert_allclose(np.bincount(group,weights=details['peak_posterior']),1.,atol=3e-15)
            assert_allclose(details['detection_probability'].sum(),original.model.score.detection_budget,atol=1e-13)
            with np.load(path.with_suffix('.npz')) as saved:
                assert_array_equal(saved['associated'],assigned)
                assert_allclose(saved['residual_hz'],residual,atol=1e-8,rtol=0)
                assert_array_equal(saved['satellite_number'],original.bank.numbers[best])
            evidence.append(dict(source_id=sid,arm=r['arm'],method=r['method'],
                actual_singleton_exact_objective_and_all_gradients=True,
                endpoint_likelihoods_gradients_and_saved_winner_arrays_replayed=True,
                strict_stationarity=audit['stationarity'],strict_accepted=audit['accepted'],
                source_input_sha256=original.source['tracking_input_sha256'],
                source_terminal_sha256=original.source['terminal_sha256'],
                group_count=len(original.observations.times_s),peak_count=len(group),
                unchanged_sigma_hz=float(original.model.score.sigma_hz),
                unchanged_relative_sigma_s=float(original.model.score.relative_sigma_s),
                unchanged_common_sigma_s=float(original.model.score.common_sigma_s),
                unchanged_detection_budget=float(original.model.score.detection_budget),
                unchanged_fixed_band_offsets_hz=shift.offsets_hz,
                calibration_transport_error_hz=closure['maximum_correction_error_hz'],
                optimization_evaluations=r['diagnostics']['evaluations']))
        print(json.dumps(dict(source_id=sid,replayed=True)),flush=True)
    save_json(HERE/'verification.json',dict(passed=True,synthetic_tests=result.testsRun,
        endpoint_count=len(evidence),evidence=evidence,
        qualification='No fit or selection; replay/audit calls are outside the optimizer allowance and cannot change saved endpoints.'))


if __name__=='__main__':main()
