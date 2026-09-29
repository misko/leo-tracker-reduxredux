import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('boundary_replay', Path(__file__).with_name('replay.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def candidate(fallback=True):
    return dict(conditioned_fallback=fallback, pre_exact=.01, pre_control=.02,
                pre_acquired=100., pre_tracking=200., refined_epoch=20,
                exact_score=.5, control_score=.2, margin=.3,
                acquired_cfo_hz=300., tracking_cfo_hz=400.)


def test_gate_restores_pre_refinement_score_and_frequency():
    original = candidate()
    result, skipped = module.gated_candidate(original, 0.)
    assert skipped and result['margin'] == -.01
    assert result['tracking_cfo_hz'] == 200.
    assert result['epoch'] == 20 and result['conditioned_cfo_hz'] is None
    assert original['tracking_cfo_hz'] == 400.


def test_gate_does_not_change_nonfallback_or_equal_threshold():
    assert not module.gated_candidate(candidate(False), 0.)[1]
    assert not module.gated_candidate(candidate(), -.01)[1]
