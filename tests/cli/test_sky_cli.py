"""Operator-surface tests for the `leo sky` commands.

The commands are driven through the real Typer application against a temporary
archive, so option parsing, observer resolution, exit codes and both output
modes are covered where they actually run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from leo.cli.app import create_cli
from leo.sky.propagation import element_line_checksum

ANCHOR = "2026-08-20T15:03:17Z"
ANCHOR_NS = 1_787_238_197_000_000_000


def _seal(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _element_sets(count: int = 6) -> str:
    """Near-equatorial orbits placed over an observer at (0, 0) at the anchor."""

    payload = ""
    for index in range(count):
        mean_anomaly = (130.0 + index * 0.6 - 2.0) % 360.0
        number = 40_000 + index
        payload += (
            _seal(f"1 {number:05d}U 26232A   26232.50000000  .00000100  00000-0  10000-4 0  9990")
            + "\n"
            + _seal(
                f"2 {number:05d}   0.5000   0.0000 0001000"
                f"  87.0000 {mean_anomaly:8.4f} 15.20000000260120"
            )
            + "\n"
        )
    return payload


@pytest.fixture
def archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "archive" / "space-track"
    directory.mkdir(parents=True)
    payload = _element_sets()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{ANCHOR_NS}-{digest}.tle").write_text(payload)
    monkeypatch.setenv("LEO_TLE_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def empty_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LEO_TLE_ROOT", str(tmp_path))
    return tmp_path


def _run(*args: str):
    return CliRunner().invoke(create_cli(), list(args))


def test_sites_lists_the_reviewed_preset_with_its_provenance() -> None:
    result = _run("sky", "sites", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.output)["payload"]
    assert [site["name"] for site in payload["sites"]] == ["spinnaker-sausalito"]
    site = payload["sites"][0]
    assert site["provenance"].startswith("OpenStreetMap")
    assert site["position_uncertainty_m"] <= 100.0


def test_sites_human_output_names_the_site() -> None:
    result = _run("sky", "sites")
    assert result.exit_code == 0
    assert "Spinnaker" in result.output


def test_snapshots_lists_the_archive(archive: Path) -> None:
    result = _run("sky", "snapshots", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.output)["payload"]
    assert len(payload["snapshots"]) == 1
    snapshot = payload["snapshots"][0]
    assert snapshot["provider"] == "space-track"
    assert snapshot["digest"].startswith("sha256:")
    assert snapshot["collected_utc_ns"] == ANCHOR_NS


def test_snapshots_reports_an_empty_archive_without_pretending(empty_archive: Path) -> None:
    result = _run("sky", "snapshots", "--json")
    assert result.exit_code == 20
    body = json.loads(result.output)
    assert body["ok"] is False
    assert body["payload"]["snapshots"] == []


def test_snapshots_rejects_an_unknown_provider(archive: Path) -> None:
    result = _run("sky", "snapshots", "--provider", "celestrak", "--json")
    assert result.exit_code == 40
    assert json.loads(result.output)["ok"] is False


def test_field_reports_objects_for_an_explicit_observer(archive: Path) -> None:
    result = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--el",
        "90",
        "--fov",
        "90",
        "--at",
        ANCHOR,
        "--json",
    )
    assert result.exit_code == 0
    report = json.loads(result.output)["payload"]["report"]
    assert report["snapshot"]["object_count"] == 6
    assert report["returned_object_count"] == len(report["objects"])
    assert (
        report["source_object_count"]
        + sum(value for key, value in report["exclusions"].items() if key != "schema_version")
        == 6
    )
    for item in report["objects"]:
        assert item["doppler"]["downlink_frequency_hz"] == pytest.approx(11.7e9)
        assert item["element_age_s"] >= 0.0


def test_field_accepts_a_reviewed_site_preset(archive: Path) -> None:
    result = _run(
        "sky",
        "field",
        "--site",
        "spinnaker-sausalito",
        "--fov",
        "90",
        "--el",
        "90",
        "--at",
        ANCHOR,
        "--json",
    )
    assert result.exit_code == 0
    observer = json.loads(result.output)["payload"]["report"]["observer"]
    assert observer["label"] == "Spinnaker, Sausalito"
    assert observer["latitude_deg"] == pytest.approx(37.858988)


def test_field_requires_an_observer(archive: Path) -> None:
    """There is no default position: an answer must not silently acquire one."""

    result = _run("sky", "field", "--at", ANCHOR, "--json")
    assert result.exit_code != 0
    assert "observer is required" in result.output


def test_field_refuses_a_site_and_coordinates_together(archive: Path) -> None:
    result = _run(
        "sky",
        "field",
        "--site",
        "spinnaker-sausalito",
        "--lat",
        "0",
        "--lon",
        "0",
        "--at",
        ANCHOR,
    )
    assert result.exit_code != 0
    assert "not both" in result.output


def test_field_rejects_an_unknown_site(archive: Path) -> None:
    result = _run("sky", "field", "--site", "nowhere", "--at", ANCHOR)
    assert result.exit_code != 0
    assert "unknown site" in result.output
    assert "spinnaker-sausalito" in result.output


def test_field_rejects_a_malformed_instant(archive: Path) -> None:
    result = _run("sky", "field", "--lat", "0", "--lon", "0", "--at", "yesterday")
    assert result.exit_code != 0
    assert "ISO-8601" in result.output


def test_field_reports_an_unavailable_archive_rather_than_an_empty_sky(
    empty_archive: Path,
) -> None:
    result = _run("sky", "field", "--lat", "0", "--lon", "0", "--at", ANCHOR, "--json")
    assert result.exit_code == 40
    body = json.loads(result.output)
    assert body["ok"] is False
    assert body["payload"] is None
    assert "no TLE snapshot is available" in body["message"]


def test_field_limit_truncates_and_says_so(archive: Path) -> None:
    result = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--el",
        "90",
        "--fov",
        "90",
        "--at",
        ANCHOR,
        "--limit",
        "2",
        "--json",
    )
    assert result.exit_code == 0
    report = json.loads(result.output)["payload"]["report"]
    assert report["returned_object_count"] <= 2
    assert report["truncated"] == (report["returned_object_count"] < report["source_object_count"])


def test_field_downlink_frequency_scales_the_predicted_doppler(archive: Path) -> None:
    def shift(downlink_hz: str) -> float:
        result = _run(
            "sky",
            "field",
            "--lat",
            "0",
            "--lon",
            "0",
            "--el",
            "90",
            "--fov",
            "90",
            "--at",
            ANCHOR,
            "--downlink-hz",
            downlink_hz,
            "--limit",
            "1",
            "--json",
        )
        assert result.exit_code == 0
        report = json.loads(result.output)["payload"]["report"]
        return report["objects"][0]["doppler"]["frequency_at_reference_hz"]

    assert shift("23400000000") == pytest.approx(2.0 * shift("11700000000"), rel=1e-9)


def test_field_human_output_states_the_evidence_limitation(archive: Path) -> None:
    result = _run(
        "sky", "field", "--lat", "0", "--lon", "0", "--el", "90", "--fov", "90", "--at", ANCHOR
    )
    assert result.exit_code == 0
    assert "Not a detection, attribution or identification" in result.output


def test_field_output_uses_candidate_only_vocabulary(archive: Path) -> None:
    """The operator surface must not imply reception or identification."""

    result = _run(
        "sky", "field", "--lat", "0", "--lon", "0", "--el", "90", "--fov", "90", "--at", ANCHOR
    )
    lowered = result.output.lower()
    for forbidden in ("detected", "acquired", "locked", "identified", "confirmed"):
        assert forbidden not in lowered


def test_sky_commands_never_write_to_the_archive(archive: Path) -> None:
    before = {path: path.stat().st_mtime_ns for path in sorted(archive.rglob("*"))}
    _run("sky", "snapshots", "--json")
    _run("sky", "field", "--lat", "0", "--lon", "0", "--el", "90", "--fov", "90", "--at", ANCHOR)
    after = {path: path.stat().st_mtime_ns for path in sorted(archive.rglob("*"))}
    assert before == after


@pytest.mark.parametrize(
    ("option", "value"),
    (
        ("--lat", "91"),
        ("--lat", "-91"),
        ("--lon", "181"),
        ("--el", "91"),
        ("--fov", "0"),
        ("--fov", "91"),
        ("--mask", "-1"),
        ("--az", "360"),
        ("--alt", "20000"),
        ("--downlink-hz", "0"),
    ),
)
def test_out_of_range_options_are_refused_with_a_message(
    archive: Path, option: str, value: str
) -> None:
    """An invalid input must never produce an empty body and a bare exit 1."""

    result = _run(
        "sky", "field", "--lat", "0", "--lon", "0", "--at", ANCHOR, option, value, "--json"
    )
    assert result.exit_code != 0
    assert result.output.strip(), "an invalid input produced no output at all"


def test_a_contract_rejection_is_reported_as_typed_json(archive: Path) -> None:
    """Anything the contracts refuse but the option bounds allow must still
    come back as a result, not as a traceback."""

    result = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--at",
        ANCHOR,
        "--label",
        "x" * 200,
        "--json",
    )
    assert result.exit_code == 10
    body = json.loads(result.output)
    assert body["ok"] is False
    assert body["payload"] is None
    assert "128 characters" in body["message"]


@pytest.mark.parametrize(("option", "value"), (("--az", "359.9999995"), ("--fov", "0.0000005")))
def test_values_the_contracts_accept_are_not_refused_by_the_cli(
    archive: Path, option: str, value: str
) -> None:
    """Click bounds cannot express an exclusive limit, so approximating one
    rejected inputs the contracts allow."""

    result = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--el",
        "90",
        "--fov",
        "90",
        "--at",
        ANCHOR,
        option,
        value,
        "--json",
    )
    assert result.exit_code == 0


def test_the_downlink_bound_matches_the_api(archive: Path) -> None:
    """One surface policy, applied identically, so a value accepted by the API
    is accepted here."""

    from leo.presentation.sky import MAXIMUM_DOWNLINK_FREQUENCY_HZ

    ok = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--el",
        "90",
        "--fov",
        "90",
        "--at",
        ANCHOR,
        "--downlink-hz",
        str(MAXIMUM_DOWNLINK_FREQUENCY_HZ),
        "--json",
    )
    assert ok.exit_code == 0

    refused = _run(
        "sky",
        "field",
        "--lat",
        "0",
        "--lon",
        "0",
        "--at",
        ANCHOR,
        "--downlink-hz",
        str(MAXIMUM_DOWNLINK_FREQUENCY_HZ * 10),
    )
    assert refused.exit_code != 0
    assert refused.output.strip()
