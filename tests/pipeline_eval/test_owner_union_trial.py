from importlib import import_module
from itertools import combinations
from pathlib import Path

import pytest

from tools.pipeline_eval.variants.carrier_continuation import votes


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("owner_union_trial")


def lane(counter, value=None, *, rx=0, channel=3, rf=11e9, edge=2):
    candidates = [] if value is None else [dict(fractional_tracking_cfo_hz=value, candidate_rank=0)]
    return dict(valid_start_counter=counter, receiver_id=rx, channel=channel,
                actual_rf_hz=rf, edge=edge, candidates=candidates)


def test_history_preserves_empty_slots_exact_rf_and_eight_second_boundary(audit):
    probes = [lane(i * 1_000_000) for i in range(13)]
    probes.insert(6, lane(5_100_000, rx=1))
    probes.append(lane(12_500_000, rf=12e9))
    probes.append(lane(13_000_000, 500., edge=1))
    target = len(probes) - 1
    recent = audit.histories(probes, {target})[target]
    assert list(recent) == [i for i in range(1, target - 1) if i != 6]

    separated = [lane(0), lane(1), lane(80_000_001, 50.)]
    assert audit.histories(separated, {2}) == {2: (1,)}


def test_ideal_donor_floor_matches_brute_force_on_small_lane(audit):
    probes = [lane(2_000_000 * k, 1_000. + 20 * k) for k in range(9)]
    kept = {4, 7, 8}
    windows = audit.histories(probes, kept)

    def feasible(paid):
        return all(len(set(window) & paid) >= 3 and any(
            probes[i]["valid_start_counter"] <= probes[k]["valid_start_counter"] - audit.MIN_AGE
            for i in set(window) & paid) for k, window in windows.items())

    other = sorted(set(range(len(probes))) - kept)
    optimum = next(len(kept) + size for size in range(len(other) + 1)
                   if any(feasible(kept | set(add)) for add in combinations(other, size)))
    paid = audit.necessary_donors(probes, kept, windows)
    assert feasible(paid) and len(paid) == optimum


def test_exported_donor_proxy_preserves_observed_votes_and_charges_missing_witness(audit):
    probes = [lane(i * 1_000_000, value) for i, value in enumerate(
        (100., 124_500., 120., 130., 140., None, 160., 201_000., 201_000.))]
    kept = {6, 8}
    windows = audit.histories(probes, kept)
    paid, diagnostic = audit.observed_donors(probes, kept, windows, votes)
    assert diagnostic == {"witnessed": 1, "full_window_charged": 1}
    assert kept <= paid and set(windows[8]) <= paid


def test_owner_mask_preserves_full_signed_factor_and_all_probe_metadata(audit):
    raw = dict(source={"probes": [lane(10., -23.10), lane(11., 14.4), lane(12.)],
                       "raw_recording_authority_digest": "original_authority", "session_id": "frozen"},
               provenance=dict(detector_sha256="sha256:abc", run_id="original"),
               delivery_clocks=[{"monotonic_ns": 14}], clock_anchor={"sample_counter": 0})
    mask = audit.owner_mask(raw, {0})
    assert mask["source"]["probes"] == [raw["source"]["probes"][0], lane(11.), lane(12.)]
    assert raw["source"]["probes"][1]["candidates"]
    assert mask["source"]["raw_recording_authority_digest"] == "original_authority"
    assert mask["source"]["session_id"] == "frozen" and mask["clock_anchor"] == raw["clock_anchor"]
    assert mask["delivery_clocks"] == raw["delivery_clocks"]
    assert mask["provenance"]["run_id"].startswith("blind-compact-")
    with pytest.raises(ValueError, match="original admitted selected factor"):
        audit.owner_mask(raw, {2})
