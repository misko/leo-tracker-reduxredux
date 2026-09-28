from types import SimpleNamespace
import time
import numpy as np
import pytest
import run_robust_search as runner
from robust_core import train_shortlist, joint_heldout_score


def test_adapter_preserves_chunk_candidate_mapping_and_joint_score():
    origin = (38., -121.)
    measured = np.array([20., 22., 24., 26.])
    training = np.array([True, True, False, False])
    predictions = np.array([[0., 2., 4., 6.], [0., 1., 2., 3.], [1., 2., 0., 1.]])
    ids = np.array([80, 20, 40])
    track = SimpleNamespace(measured_hz=measured, training_mask=training, times_s=np.arange(4))
    receiver = runner.base.point(*origin).ecef_km
    positions = receiver + np.array([[[[500., 0., 500.]]*4], [[[0., 500., 500.]]*4], [[[-500., 0., 500.]]*4]])
    bank = SimpleNamespace(source=track, position_km=positions)
    reception = [dict(observation_index=i, matched=False, detection_logit_east0=.2,
        detection_east_slope=1., ratio_mean_east0=0., ratio_east_slope=1.) for i in (2, 3)]
    evaluator = runner.RobustBranchEvaluator.__new__(runner.RobustBranchEvaluator)
    evaluator.banks = {'track': bank}
    evaluator.index = {'track': {80: 0, 20: 1, 40: 2}}
    evaluator.origin = origin
    evaluator.reception = {'track': reception}
    evaluator.ratio_variance = 1.
    evaluator.parameters = {'scale_hz': 100., 'degrees_of_freedom': 4.}
    evaluator.cache = {}
    evaluator.started = time.monotonic()
    # Deliberately return non-bank order and split prediction chunks.
    order = np.array([2, 0, 1])
    evaluator.predictions = lambda e, n: [SimpleNamespace(track_id='track',
        predictions_hz=predictions[ix, None, :], candidate_ids=ids[ix], visible=np.ones(len(ix), bool))
        for ix in (order[:1], order[1:])]
    actual = evaluator.evaluate(0., 0.)
    shortlist = train_shortlist(predictions[order], measured, training, np.ones(3, bool), scale_hz=100., df=4.)
    delta = positions[order, 0] - receiver
    east_axis = np.array([-np.sin(np.deg2rad(origin[1])), np.cos(np.deg2rad(origin[1])), 0.])
    east = (delta / np.linalg.norm(delta, axis=-1, keepdims=True)) @ east_axis
    expected = joint_heldout_score(predictions[order], east, measured, training,
        shortlist, reception, ratio_variance=1.)
    assert actual['scores'] == pytest.approx(expected['scores'])
    assert actual['tracks'][0]['candidate_ids'] == ids[order][shortlist['candidate_indices']].tolist()
    assert evaluator.evaluate(0., 0.) is actual
