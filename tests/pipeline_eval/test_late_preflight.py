import pytest

from tools.pipeline_eval.qualification import late_preflight_live_figures as figure
from tools.pipeline_eval.qualification.late_preflight_live_results import compare
from tools.pipeline_eval.qualification.late_preflight_results import replay_packet
from tools.pipeline_eval.variants.late_preflight import preflight, rf_rows


def family(norad, biases, *, rms=90, count=18):
    return [(norad, f"component-{i}", count, bias, rms) for i, bias in enumerate(biases)]


def test_repeated_same_sign_coherent_rf_is_preserved_in_both_arms():
    a = family(66259, [-70, -106, -104, -76])
    b = family(66259, [-92, -98, -129, -104])
    assert preflight(dict(c0=a, fitted_c=b)) == (True, "paired_profile_bias", (66259,))
    assert preflight(dict(c0=a, fitted_c=family(66259, [80, 90, 95, 104]))) == (
        False,
        "no_coherent_family",
        (),
    )


def test_preflight_cannot_use_single_track_or_unshared_track_points():
    rows = family(1, [90, 93], count=20) + family(2, [200], count=60)
    small = family(1, [95, 90], count=13) + family(2, [202], count=60)
    assert preflight(dict(c0=rows, fitted_c=small))[0] is False
    noisy = family(1, [65, 250])
    assert preflight(dict(c0=rows, fitted_c=noisy))[0] is False
    assert preflight(dict(c0=rows, fitted_c=[]))[1] == "unavailable_evidence"


def test_rf_adapter_extracts_only_predecision_track_statistics():
    made = dict(
        norad=1,
        component="arc",
        points=31,
        profile_bias_hz=120,
        conditional_residual_gate={"rms_hz": 91},
        compatible=True,
    )
    arm = {
        "gates": {"tracks": [made, made | {"compatible": False}]},
        "endpoint_latlon": [123, 123],
        "candidate": "pytest",
    }
    assert rf_rows(dict(c0=arm, fitted_c=arm)) == {
        "c0": [(1, "arc", 31, 120, 91)],
        "fitted_c": [(1, "arc", 31, 120, 91)],
    }


def test_live_comparison_reads_v5_conditional_rf_from_result_metrics():
    result = dict(
        status="ok",
        boundary="native",
        arms={a: {"latlon": [1, 2]} for a in ("c0", "fitted_c")},
        metrics={"c0_conditional_rms_hz": 22.0, "fitted_c_conditional_rms_hz": 11.0},
    )
    earlier = result | {"metrics": {"c0_conditional_rms_hz": 23.0}}
    pair = compare(result, earlier)
    assert pair["c0"]["rf_delta_hz"] == -1 and pair["c0"]["endpoint_delta_km"] == 0
    assert pair["fitted_c"]["rf_delta_hz"] is None


def test_a_bypass_keeps_the_post_addition_incumbent():
    blind = dict(
        id="fixture",
        native_sha256="native",
        catalog_sha256="causal",
        request_sha256="bound",
        archive_sha256="original",
        tile="same",
        preflight={"run": False},
    )
    positions = {
        "cavity": {"latlon": [1, 2], "rf_rms_hz": 9},
        "incumbent": {"latlon": [2, 3], "rf_rms_hz": 10},
        "final": {"latlon": [3, 4], "rf_rms_hz": 11},
    }
    replay, cutoff = replay_packet(
        blind,
        {
            "stages": {a: positions for a in ("c0", "fitted_c")},
            "decision": {"selected": "different"},
        },
    )
    assert replay["result"]["arms"]["c0"] == positions["incumbent"]
    assert cutoff["result"]["arms"]["c0"] == positions["cavity"]


def test_fresh_chart_rejects_a_control_with_a_different_scientific_request():
    binding = dict.fromkeys(figure.MATCH, "bound") | {"id": "roof", "frozen_request_sha256": "raw"}
    endpoint = {"latlon": [1, 2]}
    result = dict(
        status="ok", boundary="stored GLRT", metrics={}, arms={"c0": endpoint, "fitted_c": endpoint}
    )
    row = dict(
        id="roof",
        native_binding=binding,
        result=result,
        control=result,
        request={"scientific_request_sha256": "bound"},
    )
    control = dict(binding, method=figure.aligned.STOCK, request_sha256="raw", result=result)
    pair = figure.plot_pair(row, control, row["request"])
    assert [r["result"] for r in pair] == [result, result]
    with pytest.raises(ValueError, match="scientific_request_sha256"):
        figure.plot_pair(row, control, {"scientific_request_sha256": "different"})
