from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import PolynomialTrajectory
from leo.analysis.starlink.trajectory_feedback import (
    resolve_hough_replay_alias_indices_by_native_replay,
    trajectory_observations,
)
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock

_RECORDING = Path("/srv/bulk/leo/recordings/2026/08/30/cap-20260830T161800-612f7474ba73")
_STATEFUL = Path(
    "/srv/bulk/leo/analysis/cap-20260830T161800-612f7474ba73/"
    "reprocess-1faa2d3bb98e404caec494b4efb9e83b/scientific/path-standard-native/"
    "sha256:04e3d1e1ad73c59d8db04d3e6768b20ddbe330506639ec77ce77f987a46062e5/"
    "standard.native-stateful-path.v2.json"
)
_TRAJECTORY_ID = "sha256:f9e5ce354ff3a7682dc28edc7000ba7729f622bc087fd911c650002368630b3c"


def _score(value: dict[str, object]) -> PilotMethodScore:
    return PilotMethodScore(
        PilotMethod(str(value["method"])),
        float(value["exact_score"]),
        None if value["control_score"] is None else float(value["control_score"]),
        float(value["margin"]),
        float(value["residual_cfo_hz"]),
        float(value["tracking_cfo_hz"]),
    )


def _detection(value: dict[str, object]) -> PilotProbeDetection:
    candidates = tuple(
        PilotMethodCandidate(
            int(candidate["rank"]),
            int(candidate["local_epoch_sample"]),
            float(candidate["acquired_cfo_hz"]),
            tuple(_score(score) for score in candidate["scores"]),
            None if candidate["qam_accuracy"] is None else float(candidate["qam_accuracy"]),
            None if candidate["qam_evm"] is None else float(candidate["qam_evm"]),
        )
        for candidate in value["candidates"]
    )
    return PilotProbeDetection(
        NumericalStatus(str(value["status"])),
        int(value["sample_start"]),
        float(value["time_s"]),
        None if value["local_epoch_sample"] is None else int(value["local_epoch_sample"]),
        None if value["acquired_cfo_hz"] is None else float(value["acquired_cfo_hz"]),
        tuple(_score(score) for score in value["scores"]),
        None if value["qam_accuracy"] is None else float(value["qam_accuracy"]),
        None if value["qam_evm"] is None else float(value["qam_evm"]),
        str(value["reason"]),
        int(value["source_candidate_count"]),
        int(value["truncated_candidate_count"]),
        candidates,
    )


def _trajectory(value: dict[str, object]) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        str(value["trajectory_id"]),
        PilotMethod(str(value["method"])),
        int(value["polynomial_degree"]),
        float(value["reference_time_s"]),
        tuple(float(item) for item in value["coefficients_hz"]),
        float(value["start_s"]),
        float(value["end_s"]),
        tuple(str(item) for item in value["observation_ids"]),
        int(value["point_count"]),
        float(value["residual_rms_hz"]),
        float(value["bic"]),
        float(value["high_gate"]),
        int(value["em_iterations"]),
        bool(value["candidate_only"]),
    )


class _VerifiedChunkReader:
    """Sequential read-only corpus adapter that verifies every consumed shard."""

    sample_rate_hz = 10_000_000
    sample_count = 600_000_000
    receiver_ids = (0,)

    def __init__(self, stream: dict[str, object]) -> None:
        self._stream = stream

    def iter_blocks(self, *, block_samples: int):
        expected_start = 0
        for chunk in self._stream["chunks"]:
            path = _RECORDING / str(chunk["relative_path"])
            compressed = path.read_bytes()
            assert "sha256:" + hashlib.sha256(compressed).hexdigest() == chunk["compressed_sha256"]
            payload = zstd.ZstdDecompressor().decompress(
                compressed,
                max_output_size=int(chunk["uncompressed_bytes"]),
            )
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == chunk["uncompressed_sha256"]
            values = np.frombuffer(payload, dtype="<i2").reshape(int(chunk["sample_count"]), 1, 2)
            for offset in range(0, len(values), block_samples):
                block = values[offset : offset + block_samples].copy()
                interval = NanosecondIntervalV1(lower_ns=expected_start, upper_ns=expected_start)
                yield IqBlock(
                    samples=block,
                    metadata=IqBlockMetadataV1(
                        radio_id="radio_pluto_5d4d",
                        receiver_ids=(0,),
                        sample_count=len(block),
                        session_sample_start=expected_start,
                        host_request_utc_ns=interval,
                        host_request_monotonic_ns=interval,
                    ),
                )
                expected_start += len(block)


@pytest.mark.real_corpus
def test_612f7474_wrap_boundary_uses_native_replay_alias_three() -> None:
    """Bounded exact-IQ regression for the reviewed 10 MS/s alias-2 failure."""

    stateful = json.loads(_STATEFUL.read_text(encoding="utf-8"))
    science = stateful["segments"][0]["local_science"]
    manifest = json.loads((_RECORDING / "manifest.json").read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["stream_id"] == "stream-0")
    detections = tuple(_detection(item) for item in science["detections"])
    representative = next(
        item
        for item in science["residual_hough_representatives"]
        if item["trajectory"]["trajectory_id"] == _TRAJECTORY_ID
    )
    representatives = ((representative["family_id"], _trajectory(representative["trajectory"])),)
    config = production_receiver_standard_config(sample_rate_hz=10_000_000)

    resolution = resolve_hough_replay_alias_indices_by_native_replay(
        _VerifiedChunkReader(stream),  # type: ignore[arg-type]
        detections,
        representatives,
        trajectory_observations(detections),
        config.feedback,
        edge=stateful["starlink_edge"],
        alias_spacing_hz=config.segmentation.initial_hough.alias_spacing_hz,
        gate_config=config.replay_gate,
        usable_baseband_min_hz=-5_000_000.0,
        usable_baseband_max_hz=5_000_000.0,
    )

    assert resolution.alias_indices == {_TRAJECTORY_ID: 3}
    evidence = {item.alias_index: item for item in resolution.evidence}
    assert evidence[2].support_weight > evidence[3].support_weight
    assert evidence[2].median_block_corrected_margin < 0.05
    assert evidence[3].q10_block_corrected_margin > 0.60
    assert evidence[3].median_block_corrected_margin > 0.65
    assert evidence[3].selected
