from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.analysis.research.multi_radio_common_rate_protocol import (
    load_multi_radio_common_rate_protocol,
)

ROOT = Path(__file__).parents[2]
PROTOCOL = ROOT / "config" / "analysis" / "multi-radio-common-rate-protocol-v1.json"

EXPECTED_CAPTURE_IDS = (
    "cap-20260825T065355-ba3e4fb8857b",
    "cap-20260825T103607-9bd90a1a50e4",
    "cap-20260825T130425-1678069fefd1",
    "cap-20260825T150802-473cb5bbcbd6",
)


def _document() -> dict[str, object]:
    value = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_protocol_freezes_exact_policy_cohort_and_fifteen_paths() -> None:
    protocol = load_multi_radio_common_rate_protocol(PROTOCOL, repository_root=ROOT)

    assert tuple(item.session_id for item in protocol.captures) == EXPECTED_CAPTURE_IDS
    assert [len(item.paths) for item in protocol.captures] == [4, 3, 4, 4]
    assert sum(len(item.paths) for item in protocol.captures) == 15
    for capture in protocol.captures:
        assert capture.episode_stop_utc_ns - capture.episode_start_utc_ns == 1_500_000_000
        assert {item.physical_radio_id for item in capture.paths} == {
            "radio_pluto_5d4d",
            "radio_pluto_19f2",
        }
        assert len({item.path_id for item in capture.paths}) == len(capture.paths)
        for path in capture.paths:
            assert path.analysis_stop_s - path.analysis_start_s == pytest.approx(1.5)
            assert dict(path.product_digests).keys() == {
                "dealiased_trajectory_bank",
                "final_trajectory_bank",
                "path_report",
                "pilot_scan",
            }


def test_protocol_discloses_upstream_all_qin_conditioning_and_local_holdout() -> None:
    protocol = load_multi_radio_common_rate_protocol(PROTOCOL, repository_root=ROOT)
    selection = protocol.document["selection"]
    measurement = protocol.document["measurement"]

    assert isinstance(selection, dict)
    assert isinstance(measurement, dict)
    assert "even and odd Qin" in selection["upstream_conditioning_disclosure"]
    assert measurement["fit_symbols"] == "even Qin only"
    assert str(measurement["response_symbols"]).startswith("odd Qin only")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda doc: doc["authority"].update(dynamic_discovery_forbidden=False),
            "dynamic_discovery_forbidden",
        ),
        (
            lambda doc: doc["authority"].update(raw_iq_scored_before_protocol_freeze=True),
            "protocol freeze",
        ),
        (
            lambda doc: doc["captures"].pop(),
            "retain all four",
        ),
        (
            lambda doc: doc["captures"][0]["paths"].__setitem__(
                0,
                {**doc["captures"][0]["paths"][0], "physical_radio_id": "radio_pluto_dead"},
            ),
            "path identity",
        ),
        (
            lambda doc: doc["captures"][0]["paths"][0].update(
                analysis_stop_s=doc["captures"][0]["paths"][0]["analysis_stop_s"] + 0.01
            ),
            "1.5 s interval",
        ),
        (
            lambda doc: doc["captures"][0]["paths"][0]["products"]["pilot_scan"].update(
                logical_uri="bulk://analysis/unlisted/escape.json"
            ),
            "escaped",
        ),
        (
            lambda doc: doc["models"]["primary"].update(per_radio_or_path_drift_allowed=True),
            "path-specific drift",
        ),
    ],
)
def test_protocol_drift_is_denied(tmp_path: Path, mutate: object, match: str) -> None:
    document = _document()
    assert callable(mutate)
    mutate(document)

    with pytest.raises(ValueError, match=match):
        load_multi_radio_common_rate_protocol(_write(tmp_path, document), repository_root=ROOT)


def test_dataset_policy_byte_drift_is_denied(tmp_path: Path) -> None:
    document = _document()
    authority = document["authority"]
    assert isinstance(authority, dict)
    authority["dataset_policy_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="dataset policy digest"):
        load_multi_radio_common_rate_protocol(_write(tmp_path, document), repository_root=ROOT)
