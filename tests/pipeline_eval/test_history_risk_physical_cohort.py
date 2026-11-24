from copy import deepcopy

import pytest

from reports.ALGO08.v3.history_risk_physical_cohort import ARMS, CASES, MODES, reduce


def compared(case, times):
    fixed = CASES[case] == "complete"
    request = dict(recording=f"/waveform/{case}", archive=dict(root="/original", snapshots_sha256="archive"),
                   region="/offer", authority=case, session=case, native=f"{case}-short")
    argv = ["--recording", request["recording"], "--archive", "/original", "--region", "/offer"]
    flags = {"history_risk_route": True}
    cache = dict(members=1, unavailable={}, cached_pages=4, observed_file_pages=4)
    resident = cache | {"index_cache": cache}
    runs, clocks = {}, {}
    for index, (mode, elapsed) in enumerate(zip(MODES, times, strict=True), 1):
        scope = dict(command=argv.copy(), cache_before=resident, cache_after=resident,
                     clock=dict(cpu_s=elapsed, elapsed_s=elapsed, exit_code=0, started_unix_ns=index))
        clocks[mode] = scope
        decision = dict(complete=fixed, reason=None if fixed else "no_active_curvature")
        receipt = dict(decision=CASES[case], region="/offer", session_id=case, window_count=5,
                       counts=dict(processed=3, invalid_capture=2))
        science = dict(receipt=receipt, reason=decision["reason"], raw_authority=case,
                       arms={name: dict(latlon=[37., -122.] if fixed else None, rf_rms_hz=4. if fixed else None)
                             for name in ARMS})
        runs[mode] = dict(process=scope, science=science, opportunities=case,
                         digest=request["native"] if mode == "candidate" else f"{case}-full",
                         figures={str(i): i for i in range(8)} if fixed else {},
                         sidecars={"grid": 179} if fixed else None,
                         phases={"authenticated_raw_acquisition":{"cpu_s":.1,"elapsed_s":.1}} if mode == "candidate" else None)
    admission = dict(order=MODES, request=request, stock="release", setup_wall_s=.3, conditioning_bytes=0,
                     original_backing_bytes=0, commands={name: argv.copy() for name in MODES},
                     adapters={"cli": "sha"}, candidate_libraries={"native": "sha"}, machine={"cpu":2},
                     active_options=flags)
    data = dict(case=case, admission=admission, qualified=True, same_opportunities=True, runs=runs, measured_exits=clocks,
                pre_score_sha256="f"*64, geographical_and_rf={"runs": {
                mode: {"horizontal_error_km": {name: 1. if fixed else None for name in ARMS}} for mode in MODES}})
    reference = dict(installed="release", request=request, issued=5, admitted=3,
                     stock=runs["stock"] | {"native_sha256": f"{case}-full"})
    return data, reference


def flags(_):
    return {"history_risk_route": True}


def test_median_and_summed_gates_differ_and_both_arms_are_reported():
    (a, ra), (b, rb) = compared("DS30-0107", (.5, 2)), compared("DS30-0016", (6, 10))
    result = reduce([a, b], {a["case"]: ra, b["case"]: rb}, flags)
    assert result["timing"]["elapsed_s"]["median_ratio"] == pytest.approx(.425)
    assert result["timing"]["elapsed_s"]["summed_ratio"] == pytest.approx(6.5/12)
    assert result["gates"]["2x"] == dict(median=True, summed=False, both_timings_and_decisions=False)
    assert result["gates"]["1.6x"]["both_timings_and_decisions"]
    assert result["decisions"]["candidate"] == dict(complete=1, withheld=1, correct=2)
    assert result["cases"]["DS30-0107"]["stock"]["arms"]["c0"]["position"] is None
    assert result["cases"]["DS30-0016"]["candidate"]["arms"]["fitted_c"]["horizontal_error_km"] == 1.


def test_pre_cairo_receipts_require_the_renderer_to_be_off():
    (a, ra), (b, rb) = compared("DS30-0107", (.5, 2)), compared("DS30-0016", (6, 10))
    expected = {a["case"]: ra, b["case"]: rb}
    current = reduce([a, b], expected, lambda argv: flags(argv) | {"cairo_six_sheets": False, "cairo_residual_layout": False})
    assert current == reduce([a, b], expected, flags)
    with pytest.raises(ValueError, match="frozen original raw comparison"):
        reduce([a, b], expected, lambda argv: flags(argv) | {"cairo_six_sheets": True})
    with pytest.raises(ValueError, match="frozen original raw comparison"):
        reduce([a, b], expected, lambda argv: flags(argv) | {"cairo_residual_layout": True})


def test_reducer_rejects_missing_cases_saved_boundaries_and_source_drift():
    (a, ra), (b, rb) = compared("DS30-0107", (.5, 2)), compared("DS30-0016", (6, 10))
    expected = {a["case"]: ra, b["case"]: rb}
    with pytest.raises(ValueError, match="Exactly the two"):
        reduce([a], expected, flags)
    changed = deepcopy(b)
    changed["qualified"] = False
    with pytest.raises(ValueError, match="requires a qualified"):
        reduce([a, changed], expected, flags)
    changed = deepcopy(b)
    changed["runs"]["candidate"]["phases"] = None
    with pytest.raises(ValueError, match="paid raw boundary"):
        reduce([a, changed], expected, flags)
    changed = deepcopy(b)
    changed["admission"]["adapters"] = {"cli": "other"}
    with pytest.raises(ValueError, match="adapters"):
        reduce([a, changed], expected, flags)
