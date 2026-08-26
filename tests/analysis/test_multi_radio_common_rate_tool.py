from __future__ import annotations

import gzip
from itertools import pairwise
from types import SimpleNamespace

import pytest

from tools import experiment_multi_radio_common_rate as tool


def _capture_result(
    session_id: str,
    *,
    shared_rms_hz: float,
    separate_rms_hz: float,
    shared_sigma_hz_s: float,
    individual_sigma_hz_s: float,
) -> dict[str, object]:
    return {
        "capture_session_id": session_id,
        "status": "evaluable",
        "heldout_metrics": {
            "shared": {"rms_hz": shared_rms_hz},
            "separate": {"rms_hz": separate_rms_hz},
        },
        "shared_block_bootstrap_rate_sigma_hz_s": shared_sigma_hz_s,
        "separate_fits": [
            {"block_bootstrap_rate_sigma_hz_s": individual_sigma_hz_s},
            {"block_bootstrap_rate_sigma_hz_s": individual_sigma_hz_s},
        ],
    }


def test_frame_starts_follow_the_nearest_integer_750_hz_lattice() -> None:
    starts = tool._frame_starts(1_331, 2_500_000, 0.0, 1.5, 3_343)

    assert len(starts) > 1_000
    assert set(b - a for a, b in pairwise(starts)) == {3_333, 3_334}
    assert starts[0] >= 0
    assert starts[-1] + 3_343 <= 3_750_000


@pytest.mark.parametrize(
    ("shared_rms", "separate_rms", "shared_sigma", "individual_sigma", "expected"),
    (
        (40.0, 50.0, 20.0, 30.0, "favorable"),
        (60.0, 50.0, 40.0, 30.0, "adverse"),
        (40.0, 50.0, 40.0, 30.0, "mixed"),
    ),
)
def test_sharing_classification_applies_the_preregistered_joint_rule(
    shared_rms: float,
    separate_rms: float,
    shared_sigma: float,
    individual_sigma: float,
    expected: str,
) -> None:
    results = tuple(
        _capture_result(
            f"cap-{index}",
            shared_rms_hz=shared_rms,
            separate_rms_hz=separate_rms,
            shared_sigma_hz_s=shared_sigma,
            individual_sigma_hz_s=individual_sigma,
        )
        for index in range(4)
    )

    summary = tool._sharing_classification(results)  # type: ignore[arg-type]

    assert summary["classification"] == expected


def test_frame_ledger_gzip_is_byte_reproducible(tmp_path) -> None:
    measurements = (SimpleNamespace(frame_rows=({"point_id": "p0", "value": 1.25},)),)
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"

    tool._write_frame_rows(first, measurements)  # type: ignore[arg-type]
    tool._write_frame_rows(second, measurements)  # type: ignore[arg-type]

    assert first.read_bytes() == second.read_bytes()
    with gzip.open(first, "rt", encoding="utf-8") as source:
        assert source.read() == '{"point_id": "p0", "value": 1.25}\n'
