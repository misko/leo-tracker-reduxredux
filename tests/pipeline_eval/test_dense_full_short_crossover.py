from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))


def test_raw_terminal_and_standard_binding_reject_changed_packet_or_offer(research):
    from dense_full_short_crossover import validate_receipt
    from leo.contracts.digests import canonical_digest

    region = {"center": [2., 3.], "width_km": 25.}
    terminal = dict(native_sha256="native", session_id="session", region=region)
    receipt = dict(terminal_sha256=canonical_digest(terminal), session_id="session", region=region, decision="complete")
    detail = dict(input_sha256="native", terminal_sha256=receipt["terminal_sha256"], region=region,
                  raw_authority="authority", state="complete")
    validate_receipt(terminal, detail, receipt, "native", region, "session", "authority")
    for alteration in (dict(input_sha256="another"), dict(state="withheld"), dict(region={}), dict(raw_authority="other")):
        with pytest.raises(ValueError, match="do not bind"):
            validate_receipt(terminal, dict(detail, **alteration), receipt, "native", region, "session", "authority")


def test_probe_support_ignores_only_candidate_factors_and_keeps_scan_order(research):
    from dense_full_short_crossover import same_source

    probes = [dict(receiver_id=i, candidates=[dict(factor=1)], valid_start_counter=100 + i) for i in range(2)]
    short = deepcopy(probes)
    short[0]["candidates"] = []
    assert same_source(probes) == same_source(short)
    assert same_source(probes) != same_source(short[::-1])
    short[0]["valid_start_counter"] += 1
    assert same_source(probes) != same_source(short)


def test_fused_comparators_must_match_full_detector_identity_and_archive(research):
    from dense_full_short_crossover_score import validate_controls

    identity = dict(native_sha256="installed", archive="original", offer="original")
    regional = [dict(result=dict(snapshots=["first", "second"]))]
    stock = dict(identity=identity, build=dict(binary_sha256="kernel"), regional=regional)
    candidate = dict(identity=identity, fused_geography=dict(binary_sha256="kernel"), regional=regional)
    raw = dict(holder=identity, raw_result=dict(regional=regional), fused_geography_sha256="kernel",
               archive_snapshots=["first", "second"])
    validate_controls(stock, candidate, raw)
    with pytest.raises(ValueError, match="All four cells"):
        validate_controls(stock, dict(candidate, fused_geography=dict(binary_sha256="wrong")), raw)
    with pytest.raises(ValueError, match="All four cells"):
        validate_controls(stock, candidate, dict(raw, archive_snapshots=["first"]))


def test_error_screen_retains_two_arms_and_explicit_withhold(research):
    from dense_full_short_crossover_score import deltas

    first = dict(arms={"c0": dict(latlon=[2., 3.], rf_rms_hz=8., horizontal_error_km=.3),
                       "fitted_c": dict(latlon=[2., 3.], rf_rms_hz=9., horizontal_error_km=.4)},
                 solve=dict(cpu_s=6., elapsed_s=7.))
    second = deepcopy(first)
    second["arms"]["fitted_c"] = dict(latlon=None, rf_rms_hz=None, horizontal_error_km=None)
    second["arms"]["c0"]["horizontal_error_km"] = .29
    compared = deltas(first, second)
    assert compared["arms"]["c0"]["horizontal_error_km"] == pytest.approx(-.01)
    assert compared["arms"]["fitted_c"]["horizontal_error_km"] is None
    assert not compared["no_arm_worse_than_250_m"]
