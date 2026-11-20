from hashlib import sha256
from json import dumps
from types import SimpleNamespace

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import antenna_benchmark as study
from tools.pipeline_eval.qualification import study_benchmark


def test_exact_sign_ties_and_holm_fixed_count():
    assert study.exact_sign([-1, -2, -3, 0]) == (3, 0, 1, 0.25)
    assert study.exact_sign([0, 0]) == (0, 0, 2, None)
    assert study.holm([0.1, 0.01, None, 0.02]) == [0.2, 0.04, None, 0.06]


def test_tolerance_includes_exact_boundary_and_marks_missing_reference():
    hit = dict(id="case", arm="c0", method=study.HIT, error_km=1.05, status="ok", baseline_km=None)
    control = dict(hit, method=study.STOCK, error_km=1.0)
    result = study.tolerance_pairs([hit, control], [study.HIT, study.STOCK], "fresh")
    assert [r["pct"] for r in result] == [5, 10]
    assert all(r["on_hit_meets_original"] is None for r in result)
    assert all(r["on_hit_meets_control"] for r in result)
    assert all(r["on_hit_within_symmetric_control_pct"] for r in result)


def test_receiver_clock_keeps_projected_calls_and_physical_measurements_distinct():
    planned = study.clock("validation", "case", study.HIT, planned=32, position={"wall_s": 2.0})
    assert planned["planned_receiver_calls"] == 32
    assert planned["measured_receiver_calls"] is None
    assert planned["full_service_s"] is None
    assert planned["position_wall_s"] == 2.0
    actual = study.clock(
        "direct",
        "case",
        study.HIT,
        measured={
            "raw_s": 5.0,
            "assembly_s": 1.0,
            "dual_calls": 24,
            "within_20ms": 7,
            "wall_s": 8.0,
        },
        calls=32,
    )
    assert actual["planned_receiver_calls"] is None
    assert actual["measured_receiver_calls"] == 32
    assert actual["complete_detector_calls"] == 24
    assert actual["acquisition_to_native_s"] == 6.0


def test_cli_dispatches_antenna_confirmation(monkeypatch, tmp_path):
    called = []
    module = SimpleNamespace(
        run=lambda target: ("receipt", target),
        show=lambda data, target: called.append((data, target)),
    )
    monkeypatch.setattr("tools.pipeline_eval.qualification.antenna_benchmark", module)
    monkeypatch.setattr(
        study_benchmark, "render_indexed", lambda target: called.append(("gallery", target))
    )
    assert (
        cli.main(["benchmark", "--receiver", "antenna-confirmation", "--out", str(tmp_path)]) == 0
    )
    assert called == [(("receipt", tmp_path), tmp_path), ("gallery", tmp_path)]


def test_indexed_gallery_uses_only_verified_chart_ids_in_both_arms(monkeypatch, tmp_path):
    evidence, out = tmp_path / "evidence", tmp_path / "output"
    evidence.mkdir()
    out.mkdir()
    descriptor, seal = evidence / "figures.json", evidence / "figure-lock.json"
    descriptor.write_text("{}")
    seal.write_text("{}")
    digest = sha256(b"{}").hexdigest()
    (out / "chart-index.json").write_text(
        dumps(
            {
                "charts": [
                    {
                        "id": "selected",
                        "descriptor": descriptor.name,
                        "descriptor_sha256": digest,
                        "seal": seal.name,
                        "seal_sha256": digest,
                    }
                ]
            }
        )
    )
    loaded, rendered = [], []

    def load(*, methods, evidence):
        loaded.append((methods, evidence))
        return [SimpleNamespace(id="selected", page=lambda arm: ("selected", arm))]

    monkeypatch.setattr(study_benchmark.screening_figures, "charts", load)
    monkeypatch.setattr(
        study_benchmark, "render", lambda dest, books: rendered.append((dest, books))
    )
    study_benchmark.render_indexed(out, evidence)
    assert loaded == [(["selected"], evidence)]
    assert rendered == [(out, {"c0": [("selected", "c0")], "fitted_c": [("selected", "fitted_c")]})]

    seal.write_text("changed")
    with pytest.raises(ValueError, match="indexed position evidence changed"):
        study_benchmark.render_indexed(out, evidence)
