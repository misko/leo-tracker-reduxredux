from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

import leo.cli.short_window as command
from leo.cli.app import create_cli
from leo.scanner.short_window import ShortWindowAcquisition
from leo.storage.short_window import ShortWindowReader


def arguments(root: Path):
    return [
        "scan",
        "windows",
        "--host",
        "radio.example",
        "--serial",
        "explicit-serial",
        "--if-hz",
        "1000000000",
        "--if-hz",
        "1200000000",
        "--output-root",
        str(root),
    ]


def test_dry_run_requires_no_hardware_or_directory_creation(monkeypatch, tmp_path):
    def forbidden(**_):
        raise AssertionError("dry run must not instantiate a radio")

    monkeypatch.setattr(command, "default_source_factory", forbidden)
    root = tmp_path / "not-created"
    result = CliRunner().invoke(create_cli(), [*arguments(root), "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["window_samples"] == 50_000
    assert payload["window_bytes"] == 400_000
    assert payload["configuration"]["policy_id"] == "firmware-weighted-20ms-v1"
    assert payload["configuration"]["transition_budget_ms"] == 100
    assert payload["configuration"]["targets"][0]["rf_center_hz"] is None
    assert payload["configuration"]["targets"][0]["profile_id"] == "1"
    assert not root.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--duration-seconds", "1801"],
        ["--duration-seconds", "301"],
        ["--max-visits", "0"],
        ["--gain-db", "nan"],
        ["--queue-bytes", "10"],
        ["--provider", "invented"],
        ["--rf-mapping-authority", "known"],
    ],
)
def test_invalid_capture_plan_fails_before_hardware_or_storage(monkeypatch, tmp_path, extra):
    monkeypatch.setattr(
        command,
        "default_source_factory",
        lambda **_: (_ for _ in ()).throw(AssertionError("hardware")),
    )
    root = tmp_path / "not-created"
    result = CliRunner().invoke(create_cli(), [*arguments(root), *extra, "--dry-run"])
    assert result.exit_code != 0
    assert not root.exists()


def test_explicit_mapping_and_single_receiver_in_preview(tmp_path):
    result = CliRunner().invoke(
        create_cli(),
        [
            *arguments(tmp_path),
            "--dry-run",
            "--receiver",
            "1",
            "--lnb-lo-hz",
            "9750000000",
            "--rf-mapping-authority",
            "hypothesis",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["window_bytes"] == 200_000
    assert payload["configuration"]["physical_receiver_labels"] == ["RX2"]
    assert payload["configuration"]["targets"][0]["rf_center_hz"] == 10_750_000_000
    assert payload["configuration"]["targets"][0]["rf_mapping_authority"] == "hypothesis"


def test_experimental_transition_profile_is_explicit_in_preview(tmp_path):
    result = CliRunner().invoke(
        create_cli(), [*arguments(tmp_path), "--dry-run", "--transition-budget-ms", "20"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["configuration"]["transition_budget_ms"] == 20
    assert payload["assumed_uniform_gap_ms"] == 20
    assert payload["estimated_windows_with_uniform_gap"] == 3000


@pytest.mark.parametrize(
    "host, expected_uri",
    [
        ("radio.example", "ip:radio.example"),
        ("ip:192.168.2.1", "ip:192.168.2.1"),
        ("usb:1.2.0", "usb:1.2.0"),
    ],
)
def test_diagnostic_provider_preserves_explicit_transport_uris(monkeypatch, host, expected_uri):
    import leo.acquisition.short_window_iio as provider

    seen = {}
    monkeypatch.setattr(provider, "IioShortWindowSource", lambda **kwargs: seen.update(kwargs))
    command.default_source_factory(host=host, serial="explicit", provider="iio")
    assert seen["uri"] == expected_uri
    assert seen["expected_serial"] == "explicit"


def test_eight_target_ppu_plan_uses_direct_profiles_zero_through_seven(tmp_path):
    preview = command.run_short_window_command(
        host="explicit",
        serial="serial",
        if_centers_hz=tuple(1_000_000_000 + index for index in range(8)),
        output_root=tmp_path,
        dry_run=True,
    )
    assert [target["profile_id"] for target in preview["configuration"]["targets"]] == [
        str(index) for index in range(8)
    ]


def test_cli_live_capture_composes_fake_source_and_real_reader(monkeypatch, tmp_path):
    seen = {}

    class Source:
        def configure_once(self, configuration):
            seen["configuration"] = configuration

        def capture(self, target, count):
            return ShortWindowAcquisition(
                np.full((count, 2, 2), 123, dtype="<i2"),
                target.if_center_hz,
                target.if_center_hz,
                validity_authority="provider_attested",
            )

        def close(self):
            seen["closed"] = True

    def factory(**kwargs):
        seen.update(kwargs)
        return Source()

    monkeypatch.setattr(command, "default_source_factory", factory)
    result = CliRunner().invoke(
        create_cli(),
        [*arguments(tmp_path), "--max-visits", "2", "--json", "--session-id", "cli-short-window"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "complete"
    assert payload["written_windows"] == 2
    assert seen["host"] == "radio.example"
    assert seen["serial"] == "explicit-serial"
    assert seen["closed"]
    reader = ShortWindowReader(Path(payload["publication"]))
    assert len(list(reader.windows())) == 2
    updates = [json.loads(line) for line in result.stderr.splitlines()]
    assert updates[0]["state"] == "capture_complete"
    assert updates[1]["state"] == "writer_accepted"


def test_source_creation_failure_seals_zero_window_incomplete_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(
        command,
        "default_source_factory",
        lambda **_: (_ for _ in ()).throw(RuntimeError("radio unavailable")),
    )
    result = CliRunner().invoke(create_cli(), [*arguments(tmp_path), "--session-id", "failed-init"])
    assert result.exit_code != 0
    reader = ShortWindowReader(tmp_path / "failed-init")
    assert reader.manifest.status == "incomplete"
    assert "radio unavailable" in reader.manifest.failure
    assert reader.manifest.window_count == 0


def test_qnap_destination_is_rejected_before_any_write():
    with pytest.raises(ValueError, match="QNAP"):
        command.run_short_window_command(
            host="explicit",
            serial="serial",
            if_centers_hz=(10,),
            output_root=Path("/mnt/qnap01/do-not-create"),
            dry_run=True,
        )
