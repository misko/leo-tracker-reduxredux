#!/usr/bin/env python3
"""Release-local worker for the fixed 600-window native evidence protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

from leo.analysis.starlink.acceptance import NativeKnownPilotDecisionPort
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.qualification.native_release import _runtime_package_tree_digest

_SAMPLES = 150_000_000
_WINDOW_SAMPLES = 25_000
_INTERVAL_SAMPLES = 250_000
_WINDOWS = 600
_BYTES_PER_SAMPLE = 4


def _digest_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while block := os.pread(descriptor, 1024 * 1024, offset):
        digest.update(block)
        offset += len(block)
    return "sha256:" + digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iq-fd", type=int, required=True)
    parser.add_argument("--iq-sha256", required=True)
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--calibration-json", required=True)
    options = parser.parse_args()
    expected_bytes = _SAMPLES * _BYTES_PER_SAMPLE
    if os.fstat(options.iq_fd).st_size != expected_bytes:
        raise ValueError("native worker IQ snapshot has the wrong exact size")
    if _digest_fd(options.iq_fd) != options.iq_sha256:
        raise ValueError("native worker IQ snapshot digest mismatch")
    config = MatchedPilotAcceptanceConfigV1.model_validate(json.loads(options.config_json))
    calibration = ReceiverFrequencyCalibrationV1.model_validate(
        json.loads(options.calibration_json)
    )
    native = NativeKnownPilotDecisionPort(config)
    runtime_package_tree_digest = _runtime_package_tree_digest(
        Path(sys.prefix).parent
    )
    decisions = []
    for index in range(_WINDOWS):
        sample_start = index * _INTERVAL_SAMPLES
        payload = os.pread(
            options.iq_fd,
            _WINDOW_SAMPLES * _BYTES_PER_SAMPLE,
            sample_start * _BYTES_PER_SAMPLE,
        )
        if len(payload) != _WINDOW_SAMPLES * _BYTES_PER_SAMPLE:
            raise ValueError("native worker IQ window is incomplete")
        raw = np.frombuffer(payload, dtype="<i2").reshape(_WINDOW_SAMPLES, 2)
        samples = ((raw[:, 0] + 1j * raw[:, 1]) / 32_768.0).astype(np.complex64)
        decisions.append(
            native.evaluate(
                window_index=index,
                sample_start=sample_start,
                samples=samples,
                sample_rate_hz=config.sample_rate_hz,
                calibration=calibration,
            ).model_dump(mode="json")
        )
    json.dump(
        {
            "schema_version": 1,
            "iq_sha256": options.iq_sha256,
            "config_digest": config.config_digest,
            "calibration_digest": calibration.calibration_digest,
            "runtime_package_tree_digest": runtime_package_tree_digest,
            "decisions": decisions,
        },
        sys.stdout,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
