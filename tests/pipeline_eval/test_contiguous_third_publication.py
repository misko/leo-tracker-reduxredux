from importlib import import_module
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.fixture
def third(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("contiguous_third")


def native(third):
    total = 11
    excluded = [dict(visit=1, sample_start=200_000, sample_end=400_000)]
    probes = [dict(visit_index=visit, receiver_id=rx, channel=visit % 8 + 1, actual_rf_hz=10_750_000_000.,
                   edge="lower", valid_start_counter=visit * 200_000, payload_start_sample=0,
                   candidates=[dict(cfo=visit * 17 + rx, passed_fractional_margin_gate=True)])
              for visit in range(total) if visit != 1 for rx in (0, 1)]
    source = dict(session_id="scan", raw_recording_authority_digest="authority", input_manifest_sha256="inventory",
                  sample_rate_hz=10_000_000, probes=probes)
    detector = "sha256:released"
    source["analysis_manifest_sha256"] = third.native_signature(source, detector, probes)
    provenance = dict(detector_sha256=detector, excluded_windows=excluded, invalid_capture=1,
                      scope="cancellation", window_count=total, processed_windows=total - 1, run_id="original")
    return dict(source=source, provenance=provenance, last_sample_counter=total * 200_000,
                delivery_clocks=[dict(monotonic_ns=visit * 20_000_000) for visit in range(total)],
                clock_anchor={"before": {"monotonic_ns": 0}})


def test_prefix_counts_all_visits_and_copies_original_complete_pairs(third):
    original = native(third)
    before = canonical_digest(original)
    masked, accounting = third.project(original)
    assert canonical_digest(original) == before
    assert accounting["prefix_visits"] == 3
    assert accounting["admitted_prefix_stereo"] == 2  # Global visit 1 failed quality.
    assert accounting["skipped_valid_stereo"] == 8
    rows = masked["source"]["probes"]
    assert set(r["visit_index"] for r in rows if r["candidates"]) == {0, 2}
    for a, b in zip(rows, original["source"]["probes"], strict=True):
        assert a == (b if b["visit_index"] < 3 else dict(b, candidates=[]))
    for k in ("delivery_clocks", "clock_anchor", "last_sample_counter"):
        assert masked[k] == original[k]
    for k in ("raw_recording_authority_digest", "input_manifest_sha256", "session_id"):
        assert masked["source"][k] == original["source"][k]
    assert masked["source"]["analysis_manifest_sha256"] != original["source"]["analysis_manifest_sha256"]


def test_prefix_rejects_unsealed_receiver_candidates_and_missing_lane(third):
    original = native(third)
    original["source"]["probes"][4]["candidates"].clear()
    with pytest.raises(ValueError, match="archived v3 receiver provenance"):
        third.project(original)
    original["source"]["probes"].pop()
    with pytest.raises(ValueError, match="stereo visits"):
        third.project(original)


def test_published_owner_must_come_from_a_retained_measured_visit(third):
    original = native(third)
    masked, _ = third.project(original)
    from hashlib import sha256

    retained = "sha256:" + sha256(b"scan:0:0").hexdigest()
    removed = "sha256:" + sha256(b"scan:0:600000").hexdigest()
    third.calibration_owners(masked, {"c0": [(retained, 123, "conditional")]})
    with pytest.raises(ValueError, match="outside the admitted receiver factors"):
        third.calibration_owners(masked, {"fitted_c": [(removed, 123, "conditional")]})


def test_prepared_witness_rejects_post_origin_phase_or_catalogue(third):
    meta = dict(causal_cutoff_utc_ns=80, anchor_utc_ns=85, duration_s=300, receiver_factors=2400, empty_factors=1600)
    witness = dict(status="inputs_prepared", tracks=dict(metadata=meta, observations=[dict(time_s=50.)], tracks=[]),
                   sky=dict(metadata=dict(cutoff_utc_ns=80), nominal_elements={1: {"provenance": {
                       "collected_utc_ns": 75, "element_epoch_utc_ns": 69}}}),
                   phase_history=dict(cutoff_utc_ns=80, sources=[dict(collected_utc_ns=77)]),
                   phase_forecast=dict(transitions=[dict(validation_time_ns=79)]))
    assert third.observe_prepared(witness)["latest_orbit_evidence_utc_ns"] == 79
    witness["phase_forecast"]["transitions"][0]["validation_time_ns"] = 81
    with pytest.raises(ValueError, match="post-origin orbit evidence"):
        third.observe_prepared(witness)
