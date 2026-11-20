import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import armijo_finish_results as study
from tools.pipeline_eval.qualification.armijo_finish_phase_retry import prepare_remap
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import compact_finish, v5_armijo_finish


def frozen_hooks(monkeypatch, adoption):
    def original(*args, **kwargs):
        raise AssertionError("the stock optimizer should be replaced within the worker")

    position = SimpleNamespace(bounded_gauss_newton=original)
    context = SimpleNamespace(adopt_additional=lambda: adoption)
    module = ModuleType("leo.analysis.localization_v3")
    module.position = position
    module.reassociation_context = context
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return position, original, context


def test_complete_worker_keeps_the_checked_selection_and_uses_kilometres(monkeypatch, tmp_path):
    added = dict(added_points=32)
    adoption = dict(
        replay=dict(
            recovery=dict(status="qualified", source="fragment"), algo06=dict.fromkeys(ARMS, added)
        )
    )
    position, original, context = frozen_hooks(monkeypatch, adoption)

    def finish(request, result, library):
        assert (request, library) == ("the same bound request", "the same projector")
        for target, expected in ((0.019, 0.0), (0.021, 0.021)):
            fit = position.bounded_gauss_newton(
                lambda xy, target=target: xy - [target, 0], [0, 0], [-12.5, -12.5], [12.5, 12.5]
            )
            np.testing.assert_allclose(fit["parameters"], [expected, 0], atol=1e-8)
        assert context.adopt_additional() is adoption
        result.write_text(
            json.dumps(dict(status="ok", metrics=dict(reassociation_selected="A_to_B")))
        )

    monkeypatch.setattr(compact_finish, "worker", finish)
    target = tmp_path / "prediction.json"
    v5_armijo_finish.worker("the same bound request", target, "the same projector")
    result = json.loads(target.read_text())
    assert position.bounded_gauss_newton is original
    assert result["boundary"] == v5_armijo_finish.BOUNDARY
    assert result["metrics"]["checked_residual_addition"]["added_points"] == dict.fromkeys(ARMS, 32)
    assert result["metrics"]["position_optimizer"]["calls"] == 2
    assert result["metrics"]["reassociation_selected"] == "A_to_B"


def test_ok_result_cannot_skip_the_compact_finish_path(monkeypatch, tmp_path):
    frozen_hooks(monkeypatch, {})
    monkeypatch.setattr(
        compact_finish,
        "worker",
        lambda request, result, library: result.write_text('{"status":"ok","metrics":{}}'),
    )
    with pytest.raises(ValueError, match="checked residual decision was bypassed"):
        v5_armijo_finish.worker("request", tmp_path / "result.json", "library")


def test_archive_residual_rms_is_distinct_from_the_selected_conditional_metric():
    arm = dict(latlon=[38, -122], rf_rms_hz=82.0)
    row = dict(result=dict(status="ok", arms={"c0": arm}, metrics=dict(c0_conditional_rms_hz=74.0)))
    original = study.measures(dict(row, method="original_no_repair_v5"), "c0", [38, -122])
    selected = study.measures(dict(row, method="v5_armijo_finish"), "c0", [38, -122])
    assert original["published_residual_rms_hz"] == 82.0
    assert original["conditional_doppler_rms_hz"] is None
    assert selected["conditional_doppler_rms_hz"] == 74.0
    assert selected["published_residual_rms_hz"] is None


def test_control_cannot_silently_rebind_the_causal_archive(monkeypatch, tmp_path):
    binding = dict(
        id="case",
        input_sha256="bound",
        native_sha256="native",
        catalog_sha256="causal",
        request_sha256="request",
    )
    monkeypatch.setattr(study.trial, "public_binding", lambda _: binding)
    row = dict(
        binding,
        catalog_sha256="other",
        result=dict(status="missing", reason="fixture", metrics={}, boundary="fixture"),
    )
    with pytest.raises(ValueError, match="historical catalog_sha256 differs"):
        study.entry("case", "compact_finish", row, tmp_path / "unused", "archived-adapter")


def remap_context(norads):
    seed = dict(
        state=dict(phases=np.array([0.04, -0.8])),
        rows=[dict(candidate_index=1, candidate_norad=12)],
    )
    return dict(
        scan=SimpleNamespace(norads=norads),
        node=dict(seed=seed),
        means=np.array([0.62]),
        problems={a: (SimpleNamespace(reference=np.array([0.37]), labels=[1]), None) for a in ARMS},
    )


def test_only_exact_ordered_adopted_slot_gets_the_cold_phase_initializer():
    original = remap_context([11, 12, 91])
    updated, receipt = prepare_remap(original, (11, 12), 91)
    np.testing.assert_array_equal(original["node"]["seed"]["state"]["phases"], [0.04, -0.8])
    np.testing.assert_array_equal(updated["node"]["seed"]["state"]["phases"], [0.04, -0.8, 0.0])
    assert updated["problems"] is original["problems"] and updated["means"] is original["means"]
    assert receipt["old_phase_initial_seconds"] == [0.04, -0.8]
    assert receipt["added_norad"] == 91 and receipt["added_catalogue_index"] == 2
    assert receipt["prior_mean_seconds"] == [0.62]
    assert receipt["reference_seconds"] == dict.fromkeys(ARMS, [0.37])


@pytest.mark.parametrize("norads", [[12, 11, 91], [11, 91, 12], [11, 12, 92], [11, 12, 91, 92]])
def test_alignment_rejects_other_catalogue_shapes_even_if_padding_would_fit(norads):
    with pytest.raises(ValueError, match="no exact adopted catalogue-slot authority"):
        prepare_remap(remap_context(norads), (11, 12), 91)
