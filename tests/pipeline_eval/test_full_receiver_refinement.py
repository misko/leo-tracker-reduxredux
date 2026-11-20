import pytest

from tools.pipeline_eval.qualification import full_receiver_refinement as overlay
from tools.pipeline_eval.scoring import ARMS, ROLES


def samples(values):
    return [{"error_km": value} for value in values]


def test_cdf_crossings_respect_ties_and_keep_withheld_in_denominator():
    first = samples([1, 3, 4, None])
    second = samples([2, 2, 5, None])
    assert overlay.curve_crossings(first, second) == {
        "lead_changes": 2,
        "strict_leads": [
            {"leader": "first", "begin_km": 1, "end_km": 2},
            {"leader": "second", "begin_km": 2, "end_km": 3},
            {"leader": "first", "begin_km": 4, "end_km": 5},
        ],
    }
    censored = overlay.curve_crossings(samples([1, None]), samples([1, 3]))
    assert censored["strict_leads"] == [{"leader": "second", "begin_km": 3, "end_km": None}]
    with pytest.raises(ValueError, match="same offered denominator"):
        overlay.curve_crossings(first, second[:-1])


def test_native_receiver_rejects_an_unmatched_graph_or_partial_boundary():
    ident = "DS26-0010"
    binding = {k: f"bound-{k}" for k in overlay.FULL_MATCH}
    row = dict(
        binding,
        id=ident,
        recording=ident,
        method=overlay.ADAPTIVE,
        address_space_limit_mib=512,
        stages={k: {} for k in ("archive_and_peak_selection", "graph", "same_exact_backend")},
        proc_memory_kib={"VmPeak": 201844},
        result=dict(
            status="withheld",
            reason="gate",
            boundary="native",
            metrics={},
            arms={arm: {"latlon": None, "forced_latlon": [20, 10]} for arm in ARMS},
        ),
    )
    overlay.verify_native(ident, row, binding, overlay.ADAPTIVE, "same_exact_backend")
    for key, bad, message in (
        ("observation_sha256", "changed", "observation_sha256"),
        ("stages", {"graph": {}}, "complete capped"),
    ):
        with pytest.raises(ValueError, match=message):
            overlay.verify_native(
                ident, row | {key: bad}, binding, overlay.ADAPTIVE, "same_exact_backend"
            )


def test_roof_analysis_includes_every_original_role_and_separate_threshold_sets():
    ident = "DS26-0010"
    recording = dict(latlon=[0, 0.01], status="fix", wall_s=1)
    refs = {
        ident: dict(
            group="DS26",
            truth=[0, 0],
            reference={name: {arm: recording for arm in ARMS} for name in ROLES},
        )
    }
    result = dict(
        status="ok",
        arms={
            "c0": dict(latlon=[0, 0.0108]),
            "fitted_c": dict(latlon=None, forced_latlon=[0, 0.005]),
        },
    )
    methods = {overlay.ADAPTIVE: {ident: {"result": result}}}
    rows = list(overlay.scores(refs, methods))
    assert len(rows) == len(ARMS) * (len(ROLES) + len(methods))
    summary, pairs = overlay.analyze(rows, methods)
    by_key = {(r["dataset"], r["arm"], r["method"]): r for r in summary}
    c0 = by_key["all", "c0", overlay.ADAPTIVE]
    fitted = by_key["all", "fitted_c", overlay.ADAPTIVE]
    assert (c0["within_v5_5pct"], c0["within_v5_10pct"]) == (0, 1)
    assert fitted["published"] == 0 and fitted["forced_error_km"]["n"] == 1
    pair = next(
        p
        for p in pairs
        if p["dataset"] == "all"
        and p["arm"] == "fitted_c"
        and p["first"] == "baseline"
        and p["second"] == overlay.ADAPTIVE
    )
    assert pair["sets"]["within_5km"] == {
        "shared": [],
        "first_only": [ident],
        "second_only": [],
    }
