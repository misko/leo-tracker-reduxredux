import json
import runpy
from pathlib import Path

import pytest

api = runpy.run_path(str(Path(__file__).with_name("report.py")))


def rows():
    return [
        dict(
            label="one",
            dataset="DS16",
            arms={
                arm: {
                    name: dict(error_km=error, qualified=True)
                    for name, error in zip(api["NAMES"], (1, 2, 1, 3), strict=True)
                }
                for arm in api["ARMS"]
            },
        )
    ]


def test_qualified_paired_regressions_and_strict_serialization():
    result = api["summarize"](rows())
    assert result["paired_regressions"]["full"]["fitted-c"]["logparabola"]["improvements"] == 1
    assert result["paired_regressions"]["full"]["zero-c"]["newton"]["regressions"] == 1
    json.dumps(result, allow_nan=False)


def test_unqualified_no_silent_archive_substitution():
    data = rows()
    data[0]["arms"]["fitted-c"]["newton"]["qualified"] = False
    raw = api["aggregate"](data, "fitted-c", "newton")
    assert raw["position_metrics_withheld"] and "mean_km" not in raw
    fallback = api["aggregate"](data, "fitted-c", "newton", True)
    assert fallback["archive_fallbacks"] == 1 and fallback["mean_km"] == 1


def test_missing_receipt_blocks_evaluation_port(tmp_path):
    with pytest.raises(ValueError, match="Not terminal"):
        api["load_receipts"]({"members": [{"label": "one"}]}, "digest", tmp_path)


def test_wrong_label_blocks_evaluation_port(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps(dict(label="other", protocol_sha256="digest")))
    with pytest.raises(ValueError, match="Foreign receipt"):
        api["load_receipts"]({"members": [{"label": "one"}]}, "digest", tmp_path)


def test_evaluation_identity_mismatch_before_coordinate_transform():
    binding = {
        "case_binding": {
            "session_id": "id",
            "model_identity": {
                "input_manifest_sha256": "in",
                "analysis_manifest_sha256": "analysis",
                "prior_signature": "prior",
            },
        }
    }
    document = {"session_id": "other"}
    with pytest.raises(ValueError, match="session differs"):
        api["check_evaluation_identity"](document, binding, lambda _: "prior")
    document = {
        "session_id": "id",
        "input_manifest_sha256": "in",
        "analysis_manifest_sha256": "analysis",
        "configuration": {"prior": {}},
    }
    api["check_evaluation_identity"](document, binding, lambda _: "prior")
    with pytest.raises(ValueError, match="prior differs"):
        api["check_evaluation_identity"](document, binding, lambda _: "changed")


def test_frequency_lineage_preserves_failed_original_and_both_costs():
    first = dict(
        path="128/029",
        receipt="failed-original",
        status="complete-with-failures",
        elapsed_s=10,
        counts={"complete": 989, "failed": 1782},
    )
    second = dict(
        path="134/029",
        receipt="corrected-public-reader",
        status="complete",
        elapsed_s=20,
        counts={"complete": 2771},
    )
    binding = dict(frequency_lineage=[first, second], frequency_replay_elapsed_s=30)
    output = api["frequency_lineage"](binding)
    assert output["attempts"] == [first, second]
    assert output["total_elapsed_s"] == 30
    assert output["attempts"][0]["counts"]["failed"] == 1782
    json.dumps(output, allow_nan=False)
    binding["frequency_replay_elapsed_s"] = 20
    with pytest.raises(ValueError, match="costs differ"):
        api["frequency_lineage"](binding)


def test_nonfinite_frequency_lineage_cost_rejected():
    with pytest.raises(ValueError, match="Invalid frequency replay cost"):
        api["frequency_lineage"](
            dict(frequency_lineage=[dict(elapsed_s=float("nan"))], frequency_replay_elapsed_s=1)
        )


def test_score_components_assignment_support_changes_are_separate():
    original = dict(
        score_components=dict(frequency_nll=10, timing_prior=2, nuisance_prior=3, total=15),
        frequency_diagnostics=dict(
            maximum_responsibility=[0.9, 0.4],
            assigned_satellite=[1, 0],
            clutter_probability=[0.1, 0.5],
        ),
    )
    candidate = dict(
        score_components=dict(frequency_nll=9, timing_prior=3, nuisance_prior=4, total=16),
        frequency_diagnostics=dict(
            maximum_responsibility=[0.8, 0.7],
            assigned_satellite=[1, 2],
            clutter_probability=[0.2, 0.2],
        ),
    )
    effect = api["frequency_effects"](original, candidate)
    assert effect["assignment_changes"] == 1
    assert effect["original"]["assigned_rows"] == 1
    assert effect["candidate"]["assigned_rows"] == 2
    assert effect["original"]["nonclutter_mass"] == pytest.approx(1.4)
    assert effect["candidate"]["nonclutter_mass"] == pytest.approx(1.6)
    assert effect["score_component_delta"] == dict(
        frequency_nll=-1, timing_prior=1, nuisance_prior=1, total=1
    )
    json.dumps(effect, allow_nan=False)
    candidate["frequency_diagnostics"]["assigned_satellite"] = [1]
    with pytest.raises(ValueError, match="Unmatched"):
        api["frequency_effects"](original, candidate)


def test_missing_assignment_diagnostics_explicit_not_imputed():
    result = api["frequency_effects"]({}, {})
    assert not result["available"] and "unavailable" in result["reason"]
