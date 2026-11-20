import hashlib
import io
import json
from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis.graph_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.qualification import native_lean_eval
from tools.pipeline_eval.variants import native_lean


def _fixture(path, *, overlap=False):
    def peak(rank, margin, cfo, gate=True):
        return dict(
            candidate_rank=rank,
            fractional_margin=margin,
            fractional_tracking_cfo_hz=cfo,
            passed_fractional_margin_gate=gate,
        )

    probes = [
        dict(
            actual_rf_hz=11_200_000_000.0,
            candidates=[peak(0, 1, 100, False), peak(2, 0.05, 102), peak(1, 0.05, 101)],
            channel=1,
            receiver_id=rx,
            valid_start_counter=100_000_000 + (visit * 200_000 if not overlap else 0),
            visit_index=visit,
        )
        for visit in (0, 1)
        for rx in (0, 1)
    ]
    doc = dict(
        clock_anchor=dict(
            sample_counter=100_000_000, before={"realtime_ns": 123}, after={"realtime_ns": 125}
        ),
        last_sample_counter=120_000_000,
        source=dict(probe_ms=20, probes=probes, sample_rate_hz=10_000_000, session_id="test"),
    )
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(payload)
    return dict(path=str(path), sha256=hashlib.sha256(payload).hexdigest())


def test_archive_winner_keeps_margin_gate_ties_and_original_time(tmp_path):
    path = tmp_path / "native.json"
    record = _fixture(path)
    clock, lanes, counts = native_lean.peak_lanes(record, 4, 123)
    assert clock == dict(anchor_utc_ns=124, cutoff_utc_ns=123, duration_s=2.0)
    assert lanes == {(11.2e9, rx, 1): [(0.01, 101), (0.03, 101)] for rx in (1, 2)}
    assert counts == dict(native_bytes=path.stat().st_size, probes=4, winning_peaks=4)


def test_archive_fails_closed_before_fitting_on_digest_or_overlap(tmp_path):
    path = tmp_path / "native.json"
    record = _fixture(path)
    with pytest.raises(ValueError, match="digest"):
        native_lean.peak_lanes(dict(record, sha256="0" * 64), 4, 123)
    with pytest.raises(ValueError, match="count"):
        native_lean.peak_lanes(record, 3, 123)
    with pytest.raises(ValueError, match="overlapping"):
        native_lean.peak_lanes(_fixture(path, overlap=True), 4, 123)


def test_verified_reader_preserves_bytes_without_seek_and_caps_each_block():
    source = io.BytesIO(b"start end")
    reader = native_lean.VerifiedBlocks(source)
    with pytest.raises(ValueError, match="bounded"):
        reader.read(native_lean.BLOCK_BYTES + 1)
    assert reader.read(5) == "start"
    reader.finish(hashlib.sha256(b"start end").hexdigest())
    assert reader.bytes == source.tell() == 9


def test_graph_arm_preserves_original_alias_resolved_track_samples():
    times = np.arange(1.0, 81.0, 2)
    unwrapped = -2300 * times - 3 * times**2
    config = TrackConfig()
    folded = unwrapped - config.alias_spacing_hz * np.rint(unwrapped / config.alias_spacing_hz)
    baseline = fit_lane(times, folded, config)
    assert baseline["tracks"]
    lanes = {(11.2e9, 1, 2): list(zip(times, folded, strict=True))}
    actual = native_lean.graph_projection(lanes, asdict(config))
    for row, original in zip(actual, baseline["tracks"], strict=True):
        ids = sorted(original["indices"], key=times.__getitem__)
        assert row["times"] == times[ids].tolist()
        assert (
            row["values"]
            == (folded[ids] + config.alias_spacing_hz * baseline["alias_lifts"][ids]).tolist()
        )


def test_matched_claim_binds_prepared_bytes_and_each_calibration_arm():
    result = dict(status="ok", reason=None, arms={"c0": {"latlon": [1.0, 2.0]}})
    candidate = dict(result=result, observation_sha256="expected")
    assert native_lean_eval.same_result(candidate, candidate)
    assert not native_lean_eval.same_result(candidate, dict(candidate, observation_sha256="other"))
