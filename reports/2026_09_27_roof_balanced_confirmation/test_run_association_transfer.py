from types import SimpleNamespace
import math
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_association_transfer as runner


def test_runner_shortlist_call_matches_public_adapter_signature():
    import ast
    import inspect
    tree = ast.parse(Path(runner.__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "train_shortlist"]
    assert len(calls) == 1
    call = calls[0]
    inspect.signature(runner.train_shortlist).bind(
        *([None] * len(call.args)), **{kw.arg: None for kw in call.keywords})


def fixture():
    rows = (
        SimpleNamespace(receiver_id="rx0", east=np.array([-.4, .2, .7])),
        SimpleNamespace(receiver_id="rx1", east=np.array([.1, -.3, .8])),
    )
    track = SimpleNamespace(log_weights=np.log([.2, .3, .5]), rows=rows)
    tensor = SimpleNamespace(
        detection_design=np.zeros((3, 2, 2)), ratio_design=np.zeros((3, 2, 2)))
    schema = SimpleNamespace(detection_east_mean=.15, detection_east_scale=.5,
                             ratio_east_mean=-.2, ratio_east_scale=.25)
    return track, tensor, schema


def test_direction_modes_transform_raw_east_before_standardizing():
    track, tensor, schema = fixture()
    normal_d, normal_r = runner.directional_design(track, tensor, schema, "normal")
    reverse_d, reverse_r = runner.directional_design(track, tensor, schema, "reversed")
    for n, row in enumerate(track.rows):
        sign = 1 if row.receiver_id == "rx0" else -1
        assert np.allclose(normal_d[:, n, -1],
                           (sign * row.east-schema.detection_east_mean)/schema.detection_east_scale)
        assert np.allclose(reverse_d[:, n, -1],
                           (-sign * row.east-schema.detection_east_mean)/schema.detection_east_scale)
        assert np.allclose(normal_r[:, n, -1],
                           (row.east-schema.ratio_east_mean)/schema.ratio_east_scale)
        assert np.allclose(reverse_r[:, n, -1],
                           (-row.east-schema.ratio_east_mean)/schema.ratio_east_scale)
    assert not np.allclose(reverse_d, -normal_d)  # nonzero scaler center matters


def test_null_direction_is_candidate_invariant():
    track, tensor, schema = fixture()
    detection, ratio = runner.directional_design(track, tensor, schema, "null")
    assert np.allclose(detection, detection[[0]])
    assert np.allclose(ratio, ratio[[0]])


def test_summary_keeps_equal_track_and_occupied_second_estimands():
    def score(value):
        return {"baseline_mean_nll": value+1, "reception_mean_nll": value,
                "improvement_baseline_minus_reception": 1.}
    rows = [{"weight_seconds": 1., "held_count": 2,
             "normal": score(1), "reversed": score(2), "null": score(3)},
            {"weight_seconds": 3., "held_count": 4,
             "normal": score(5), "reversed": score(6), "null": score(7)}]
    result = runner.summarize(rows)
    assert result["tracks"] == 2 and result["held_observations"] == 6
    assert result["normal_reception_mean_nll_equal_track"] == 3
    assert result["normal_reception_mean_nll_occupied_second_weighted"] == 4


def test_reception_loglik_rejects_failed_quadrature(monkeypatch):
    track, tensor, schema = fixture()
    tensor = SimpleNamespace(detection_design=tensor.detection_design,
                             ratio_design=tensor.ratio_design,
                             matched=np.array([True, False]), log_ratio=np.array([0., 0.]))
    calls = iter((np.zeros(3), np.ones(3)))
    monkeypatch.setattr(runner.detection_core, "candidate_detection_loglik",
                        lambda *args, **kwargs: next(calls))
    theta = np.zeros(5)
    layout = SimpleNamespace(detection_size=2, ratio_size=2)
    with pytest.raises(ValueError, match="quadrature"):
        runner.reception_loglik(track, tensor, schema, theta, layout, [0, 1], 1., 1., "normal")


def test_atomic_refuses_overwrite(tmp_path):
    target = tmp_path / "result.json"; target.write_text("existing")
    with pytest.raises(FileExistsError): runner._atomic(target, {})
