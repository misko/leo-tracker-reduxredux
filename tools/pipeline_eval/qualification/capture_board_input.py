"""Independently replay the archived CI16 reader behind the folded input binding."""

import argparse
from pathlib import Path

import numpy as np

from ..__main__ import local_output, save_json
from ..variants.iq_stream import load_windows
from .capture_board_folded import FIXTURE, REPORT, digest, file_sha, load_fixture
from .full_v5_check import BULK, _load_case


def audit(path):
    record, arrays, _ = load_fixture(path)
    case = _load_case(record["recording"])
    segment = case["recording"]["segments"][record["segment"]]
    if segment["sha256"] != record["segment_sha256"]:
        raise ValueError("capture argument file has another segment binding")
    (window,) = load_windows(
        dict(
            recording_path=str(BULK / segment["path"]),
            recording_sha256="sha256:" + segment["sha256"],
        ),
        [record["sequence"]],
    )
    if record["receiver"] not in window.receiver_ids:
        raise ValueError("capture argument source named an unknown receiver")
    lane = window.receiver_ids.index(record["receiver"])
    samples = window.samples[:, lane, :]
    values = samples[:, 0].astype("float64") + 1j * samples[:, 1]
    if (
        window.iq_sha256 != record["iq_sha256"]
        or "sha256:" + digest(window.samples.tobytes()) != record["iq_sha256"]
        or window.sample_rate_hz != record["sample_rate_hz"]
        or not np.array_equal(arrays["samples"], values)
    ):
        raise ValueError("folded body did not consume the exact archived receiver lane")
    return dict(
        fixture_manifest_sha256=file_sha(path),
        recording=record["recording"],
        segment=record["segment"],
        sequence=record["sequence"],
        receiver=record["receiver"],
        sample_rate_hz=window.sample_rate_hz,
        iq_sha256=window.iq_sha256,
        segment_sha256=segment["sha256"],
        ci16_to_complex128_exact=True,
        ci16_shape=window.samples.shape,
        edge=window.target["edge"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--out", type=Path, default=REPORT / "raw-input-audit.json")
    args = parser.parse_args()
    save_json(local_output(args.out), audit(args.fixture))
