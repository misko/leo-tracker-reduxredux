import numpy as np
import pytest
from paired_reception_evaluator import score_variants


def test_rx_calibration_change_preserves_frequency_and_shortlist():
    pred=np.array([[0.,0.,0.],[0.,10.,10.]])
    east=np.array([[-1.,-1.,-1.],[1.,1.,1.]])
    short=dict(candidate_indices=[0,1],profiled_cfo_hz=[0.,0.],
        log_weights=[np.log(.8),np.log(.2)],scale_hz=100.,degrees_of_freedom=2.)
    rx=dict(observation_index=1,matched=True,detection_logit_east0=0.,
        detection_east_slope=1.,ratio_mean_east0=0.,ratio_east_slope=1.,log_margin_ratio_rx1_rx0=0.)
    variants={'old':([rx],1.),'clone':([dict(rx)],1.),'new':([dict(rx,detection_east_slope=3.)],.5)}
    result=score_variants(pred,east,np.zeros(3),np.array([True,False,False]),short,variants)
    assert result['old']==result['clone']
    assert result['new']['scores']['D']==pytest.approx(result['old']['scores']['D'],abs=1e-12)
    assert result['new']['scores']['D_plus_geometry']!=pytest.approx(result['old']['scores']['D_plus_geometry'])
    assert short['candidate_indices']==[0,1]


def test_empty_variant_set_is_rejected():
    with pytest.raises(ValueError,match='frequency'):
        score_variants(None,None,None,None,None,{})


def test_full_evaluator_matches_original_with_reordered_candidates():
    """Exercise direction indexing and unequal track weights, not just core scoring."""
    from types import SimpleNamespace
    import time
    from paired_reception_evaluator import PairedEvaluator, runner

    origin = (37.8, -122.4)
    receiver = np.asarray(runner.base.point(*origin).ecef_km)
    banks, blocks, reception = {}, [], {}
    for tid, times in ((11, [0., .2, .5, .8]), (22, [0., 1., 2., 3.])):
        track = SimpleNamespace(track_id=tid, times_s=np.asarray(times),
            measured_hz=np.array([0., 10., 20., 30.]),
            training_mask=np.array([True, True, False, False]))
        # Storage and prediction chunks deliberately have different ID order.
        positions = np.stack([np.tile(receiver + shift, (4, 1))
            for shift in ([100., 300., 200.], [-100., -300., 200.])])[:, None]
        banks[tid] = SimpleNamespace(source=track, position_km=positions)
        for cid, predicted in ((200, [0., 9., 18., 27.]), (100, [0., 11., 22., 33.])):
            blocks.append(SimpleNamespace(track_id=tid, candidate_ids=np.array([cid]),
                predictions_hz=np.asarray(predicted, float)[None, None, :],
                visible=np.array([True])))
        reception[tid] = [dict(observation_index=i, matched=True,
            detection_logit_east0=.2, detection_east_slope=1.,
            ratio_mean_east0=.1, ratio_east_slope=.5,
            log_margin_ratio_rx1_rx0=.3) for i in (2, 3)]
    original_class = runner.frozen.original.RobustBranchEvaluator
    original, paired = original_class.__new__(original_class), PairedEvaluator.__new__(PairedEvaluator)
    for evaluator in (original, paired):
        evaluator.banks = banks
        evaluator.index = {tid: {100: 0, 200: 1} for tid in banks}
        evaluator.origin = origin
        evaluator.predictions = lambda east, north: blocks
        evaluator.parameters = dict(scale_hz=100., degrees_of_freedom=2.)
        evaluator.cache = {}
        evaluator.started = time.monotonic()
        evaluator.reception = reception
        evaluator.ratio_variance = .2
    paired.variants = {'old': (reception, .2), 'clone': (reception, .2)}
    expected = original.evaluate(0., 0.)
    actual = paired.evaluate(0., 0.)
    assert actual['weight_seconds'] == expected['weight_seconds'] == 5
    assert actual['variant_scores']['old'] == pytest.approx(expected['scores'], abs=1e-12)
    assert actual['variant_scores']['clone'] == actual['variant_scores']['old']
    assert paired.evaluate(0., 0.) is actual
