from dataclasses import replace
from types import SimpleNamespace

import pytest

import leo.application.scanner_tracking as tracking
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.storage.scanner_tracking import ScannerTrackingStore
from tests.analysis.test_persistent_hop_trajectory import _candidate
from tests.application.test_persistent_hop_tracking import _site, _snapshot_payload

PNG = b"\x89PNG\r\n\x1a\nfixture"


def source(rate=2_500_000, mode="adaptive", origin=2**54):
    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id="scan-test",
        session_start_device_sample_counter=origin,
        sample_rate_hz=rate,
        begin_before_realtime_ns=1_788_400_000_000_000_000,
        begin_before_monotonic_ns=1_000_000_000,
        begin_after_realtime_ns=1_788_400_000_002_000_000,
        begin_after_monotonic_ns=1_002_000_000,
        terminal_realtime_ns=1_788_400_040_000_000_000,
        terminal_monotonic_ns=41_000_000_000,
    )
    c = TrackingCandidate(0, rate // 25000, 0.25, 1234.5, 0.15, 0.05, 0.1, True)
    probes = tuple(
        TrackingProbe(
            i,
            0,
            0,
            0,
            1,
            "lower",
            10_709_687_500.0,
            origin + round(t * rate),
            i * rate * 120 // 1000,
            (c,),
        )
        for i, t in enumerate((0, 1, 3))
    )
    digest = canonical_digest({"source": "fixture"})
    return TrackingInput(
        "scan-test", mode, rate, "radio-test", 1, digest, digest, digest, timing, True, probes
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["fixed", "adaptive"])
def test_projection_preserves_physical_units_actual_gaps_and_large_counters(rate, mode):
    data = source(rate, mode)
    rows = project_scanner_candidates(data)
    assert [r.measured_cfo_hz for r in rows] == [1234.5] * 3
    assert rows[1].support_center_utc_ns - rows[0].support_center_utc_ns == 1_000_000_000
    assert rows[2].support_center_utc_ns - rows[1].support_center_utc_ns == 2_000_000_000
    small = project_scanner_candidates(source(rate, mode, origin=100))
    assert [r.support_center_utc_ns for r in rows] == [r.support_center_utc_ns for r in small]
    assert all(r.source_sample_end > r.source_sample_start for r in rows)


def test_rate_equivalence_and_overlap_rejection():
    low, high = [project_scanner_candidates(source(r))[0] for r in (2_500_000, 5_000_000)]
    assert abs(low.support_center_utc_ns - high.support_center_utc_ns) < 4_000
    data = source()
    overlapping = replace(data.probes[0], probe_index=1, probe_start_ms=10)
    assert len(project_scanner_candidates(replace(data, probes=(*data.probes, overlapping)))) == 3


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["fixed", "adaptive"])
def test_known_doppler_rate_recovers_across_rates_and_modes(rate, mode):
    data = source(rate, mode)
    base = data.probes[0]
    probes = tuple(
        replace(
            base,
            visit_index=i,
            valid_start_counter=base.valid_start_counter + i * rate,
            payload_start_sample=i * rate * 120 // 1000,
            actual_rf_hz=11_200_000_000.0,
            candidates=(
                replace(base.candidates[0], fractional_tracking_cfo_hz=50000.0 - 2000.0 * i),
            ),
        )
        for i in range(31)
    )
    result = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(replace(data, probes=probes))
    )
    assert result.tracklets
    longest = max(result.tracklets, key=lambda t: len(t.points))
    assert longest.normalized_rate_hz_per_s == pytest.approx(-2000.0, abs=1e-6)
    assert longest.residual_rms_hz < 1e-6


@pytest.mark.parametrize("fault", ["missing-utc", "wrong-rate", "unqualified"])
def test_projection_rejects_missing_or_mismatched_authority(fault):
    data = source()
    if fault == "missing-utc":
        data = replace(data, timing=None)
    elif fault == "wrong-rate":
        data = replace(data, sample_rate_hz=5_000_000)
    else:
        data = replace(data, qualified=False)
    with pytest.raises(ValueError):
        project_scanner_candidates(data)


def service(tmp_path, monkeypatch, *, archive_error=False, clock=lambda: 0):
    # Real reconstruction of known tracks; only the costly catalogue matcher is fault-injected.
    rows = tuple(
        _candidate(
            lane=lane,
            point=p,
            normalized_rate_hz_per_s=-2000,
            normalized_intercept_hz=50000,
            alias_index=0,
        )
        for lane in range(2)
        for p in range(31)
    )
    monkeypatch.setattr(tracking, "project_scanner_candidates", lambda _: rows)
    raw = _snapshot_payload()

    def select(_):
        if archive_error:
            raise ValueError("no causal snapshot")
        return SimpleNamespace(
            provider="space-track",
            collected_utc_ns=1_780_000_000_000_000_000,
            digest=sha256_digest(raw.encode()),
        )

    store = ScannerTrackingStore(tmp_path, read_only=False)

    def fail(*args, **kwargs):
        raise ValueError("eligible satellite propagation failed")

    runner = tracking.ScannerTrackingService(
        inputs=SimpleNamespace(load=lambda _: source()),
        products=store,
        tle_archive=SimpleNamespace(select_latest_before=select, read=lambda _: raw),
        observer_site=_site(),
        renderer=lambda *a, **k: PNG,
        matcher=fail,
        clock=clock,
    )
    return runner, store


def test_catalogue_failure_keeps_trajectory_png_and_reason(tmp_path, monkeypatch):
    runner, store = service(tmp_path, monkeypatch, archive_error=True)
    result = runner.run("scan-test")
    assert result.state == "complete"
    assert result.product.trajectory_state == "complete"
    assert result.product.tle_state == "unavailable"
    assert "no causal snapshot" in result.product.reasons[0]
    assert store.artifact("scan-test", "trajectory") == PNG
    assert runner.run("scan-test") == result


def test_budget_resume_and_failed_group_receipts(tmp_path, monkeypatch):
    clock = iter([0, 200])
    runner, store = service(tmp_path, monkeypatch, clock=lambda: next(clock))
    first = runner.run("scan-test")
    assert first.state == "running" and first.product.attempted_group_count == 0
    assert store.artifact("scan-test", "trajectory") == PNG
    runner.clock = lambda: 0
    final = runner.run("scan-test")
    assert final.state == "complete" and final.product.attempted_group_count > 0
    assert final.product.tle_state == "unavailable"
    assert "eligible satellite propagation failed" in final.product.unscored_groups[0].reason
    assert store.artifact("scan-test", "trajectory-tle") == PNG
    assert final.product.attempted_group_count == len(final.product.unscored_groups)


def test_ineligible_groups_do_not_consume_matching_slots(tmp_path, monkeypatch):
    runner, _ = service(tmp_path, monkeypatch)
    rows = tuple(
        _candidate(
            lane=0,
            point=p,
            normalized_rate_hz_per_s=-2000,
            normalized_intercept_hz=50000,
            alias_index=0,
        )
        for p in range(12)
    )
    monkeypatch.setattr(tracking, "project_scanner_candidates", lambda _: rows)
    result = runner.run("scan-test").product
    assert result.physical_group_count > 0
    assert result.eligible_group_count == result.attempted_group_count == 0
    assert result.tle_state == "no-eligible-groups"
