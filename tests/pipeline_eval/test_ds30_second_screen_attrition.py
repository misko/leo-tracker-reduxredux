import json
from fractions import Fraction

import pytest

from reports.ALGO08.v3.ds30_second_screen_attrition import OFFER, concordance, measured_screen, read_witness, retry_policy


def support():
    return dict(full_curved=2600, initial_curved=1731, curved_restored=478, rechecked_curved=1809,
                cold_rejected_tracks=["initial"], second_curved_rejections=["track1", "track2"])


def test_integer_count_uses_measurements_and_distinguishes_skip_from_zero():
    assert measured_screen(support()) == dict(entered=2209, retained=1809, dropped=400, initial=1731, restored=478)
    assert measured_screen({k: v for k, v in support().items() if k != "curved_restored"}) is None
    assert measured_screen(support() | dict(rechecked_curved=2209)) is None
    assert measured_screen(support() | dict(curved_restored=True)) is None
    assert measured_screen(support() | dict(rechecked_curved=2210)) is None
    old = dict(full_curved=100, initial_curved=100, cold_rejected_tracks=[])
    assert measured_screen(old) is None
    assert measured_screen(old | dict(rechecked_curved=100, second_curved_rejections=[]))["dropped"] == 0


def test_witness_binds_original_terminal_and_keeps_fallback_separate(tmp_path):
    offer = {"center": [0, 0]}
    native, terminal, owners = "detector", "terminal", {"c0": "alpha", "fitted_c": "beta"}
    result = dict(outcome="complete", native_sha256=native,
                  raw_identity=dict(region_sha256=OFFER, session_id="session", archive_sha256="archive", causal_cutoff_utc_ns=12),
                  evidence=dict(receipt={"terminal_sha256": terminal, "region": offer}, raw_authority="raw", owners=owners))
    attempt = dict(decision="fallback", repair={"status": "rejected"}, support=support(), fallback_clocks={"elapsed_s": 7.})
    risk = dict(choice={"route": "lean", "census": {"cutoff_utc_ns": 12}}, lean_attempts=[attempt])
    witness = dict(evidence=dict(detail=dict(region=offer, state="complete", input_sha256=native, terminal_sha256=terminal,
                                            session_id="session", raw_authority="raw"), owner_maps=owners),
                   source_sha256={"screen": "pinned"}, solver_recipe={"archive_sha256": "archive"},
                   ports={"history_risk": risk})
    file = tmp_path / "exact-named-raw-witness.json"
    file.write_text(json.dumps(witness))
    actual = read_witness(result, tmp_path, offer, {"screen": "pinned"})
    assert (actual["route"], actual["repair"], actual["counts"]["dropped"]) == ("fallback", "rejected", 400)
    assert actual["fallback_clocks"]["elapsed_s"] == 7.
    assert read_witness(result, tmp_path, offer, {"screen": "stale"})["state"] == "unbound_screen_source"
    attempt.update(decision="complete", repair={"status": "complete"})
    file.write_text(json.dumps(witness))
    assert read_witness(result, tmp_path, offer, {"screen": "pinned"})["route"] == "accepted_repair"
    risk["lean_attempts"].append(attempt)
    file.write_text(json.dumps(witness))
    assert read_witness(result, tmp_path, offer, {"screen": "pinned"})["state"] == "ambiguous_screen_attempt"
    witness["evidence"]["detail"]["terminal_sha256"] = "another worker"
    file.write_text(json.dumps(witness))
    assert read_witness(result, tmp_path, offer, {"screen": "pinned"})["state"] == "unbound_witness"


def test_exact_ties_in_concordance():
    rows = [(Fraction(1, 10), 1.), (Fraction(2, 20), 2.), (Fraction(3, 10), 3.)]
    result = concordance(rows)
    assert result["n"] == 3 and result["signal_tied"] == 1
    assert result["concordant"] == 2 and result["discordant"] == 0
    assert result["tau_b"] == pytest.approx(2/6**.5)
    assert concordance(rows[:2])["tau_b"] is None


def test_round_threshold_charges_full_retry_and_preserves_no_signal_outcome():
    stock = dict(elapsed_s=10., cpu_s=8., c0_error_km=.5, fitted_c_error_km=2.5)
    candidate = dict(elapsed_s=4., cpu_s=3., c0_error_km=2., fitted_c_error_km=1.5)
    rows = [dict(case="exact", signal={"counts": {"entered": 20, "dropped": 2}}, installed=stock, successor=candidate),
            dict(case="below", signal={"counts": {"entered": 21, "dropped": 2}}, installed=stock, successor=candidate),
            dict(case="missing", signal={"state": "screen_not_run"}, installed=stock, successor=candidate)]
    policy = retry_policy(rows)
    assert policy["retried"] == ["exact"]
    assert policy["clocks"]["elapsed_s"]["total_s"] == 22.
    assert policy["clocks"]["cpu_s"]["total_s"] == 17.
    assert policy["outcomes"]["c0"]["retry"] == {"fixes": 3, "within_1km": 1, "within_2km": 3}
    assert policy["outcomes"]["fitted_c"]["retry"] == {"fixes": 3, "within_1km": 0, "within_2km": 2}
