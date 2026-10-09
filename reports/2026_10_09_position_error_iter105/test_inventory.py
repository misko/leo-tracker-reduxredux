"""Reference-independent full failure coverage and deduplication."""

import copy

from inventory import pilot_members, regional_triggers


def binding(region="baseline", retained=True, spacing=5):
    return dict(
        source="B7",
        region=region,
        basin="point:1:2",
        retained_baseline=retained,
        baseline_spacing_km=spacing,
        checkpoint_binding="binding",
        configuration_signature=region,
        input_manifest_sha256="input",
        score_prior_signature="score",
        checkpoint_attempts=[
            dict(
                available=True,
                contains_coarse_fit=True,
                value_sha256="coarse",
                bootstrap_sha256="bootstrap",
                key="b7-shared:point:1:2",
            )
        ],
    )


def test_sep50_failure_included_even_when_not_retained_by_baseline():
    member = dict(
        dataset="POST18-development",
        label="m1",
        session_id="scan1",
        failure_bindings=[binding("sep50", False, None)],
    )
    rows = pilot_members({"members": [member]})
    assert len(rows) == 1 and len(rows[0]["triggers"]) == 1
    assert rows[0]["triggers"][0]["source_passes"][0]["region"] == "sep50"


def test_identical_input_model_point_deduplicates_passes_without_spacing_filter():
    member = dict(
        dataset="POST18-development",
        label="m1",
        session_id="scan1",
        failure_bindings=[binding(), binding("sep25", True, 10), binding("sep50", False, 20)],
    )
    row = pilot_members({"members": [member]})[0]
    assert len(row["triggers"]) == 1 and len(row["triggers"][0]["source_passes"]) == 3
    changed = copy.deepcopy(member)
    changed["failure_bindings"][1]["checkpoint_attempts"][0]["value_sha256"] = "different-model"
    assert len(pilot_members({"members": [changed]})[0]["triggers"]) == 2


def test_missing_bootstrap_is_accounted_not_excluded():
    failure = binding()
    failure["checkpoint_attempts"] = []
    member = dict(
        dataset="POST18-development", label="m1", session_id="scan1", failure_bindings=[failure]
    )
    row = pilot_members({"members": [member]})[0]
    assert not row["triggers"] and len(row["unavailable"]) == 1


def test_numerical_regional_trigger_all_grid_levels_preserves_originals():
    region = dict(
        points={"point:1:2": {"result": {"bootstrap": {"vector": [1, 2]}}}},
        searches={"V16": {"evaluations": [{"east_km": 1, "north_km": 2, "spacing_km": 5}]}},
        failures=[{"basin": "point:1:2", "stage": "calibration"}],
    )
    before = copy.deepcopy(region)
    result = regional_triggers(
        {"baseline": region, "sep50": region},
        input_digest="input",
        score_signature="prior-score",
        bank_signature="bank",
    )
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["spacing_km"] == 5
    assert result["candidates"][0]["source_passes"] == ["baseline", "sep50"]
    assert region == before


def test_different_local_constraint_radii_do_not_deduplicate():
    small = dict(
        points={"point:1:2": {"result": {"bootstrap": {}}}},
        searches={"V16": {"evaluations": [{"east_km": 1, "north_km": 2, "spacing_km": 5}]}},
        failures=[{"basin": "point:1:2", "stage": "calibration"}],
    )
    large = copy.deepcopy(small)
    large["searches"]["V16"]["evaluations"][0]["spacing_km"] = 40
    result = regional_triggers(
        {"small": small, "large": large},
        input_digest="input",
        score_signature="score",
        bank_signature="bank",
    )
    assert len(result["candidates"]) == 2
    assert {row["identity"]["local_radius_km"] for row in result["candidates"]} == {
        25.0,
        40 / 2**0.5,
    }
