from __future__ import annotations

import configparser
import json
import shutil
import subprocess
from pathlib import Path

from typer.core import TyperGroup
from typer.main import get_command

from leo.cli import create_cli

PROJECT_ROOT = Path(__file__).parents[2]
UNIT_ROOT = PROJECT_ROOT / "deploy" / "systemd"
ENV_EXAMPLE = PROJECT_ROOT / "deploy" / "etc" / "leo" / "leo.env.example"
RUNBOOK = PROJECT_ROOT / "docs" / "operations" / "runbook.md"


def _unit(name: str) -> configparser.ConfigParser:
    # systemd permits repeated list-valued directives such as Environment=.
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    with (UNIT_ROOT / name).open(encoding="utf-8") as stream:
        parser.read_file(stream)
    return parser


def _services() -> tuple[Path, ...]:
    return tuple(sorted(UNIT_ROOT.glob("*.service")))


def test_expected_service_and_timer_templates_exist() -> None:
    expected = {
        "leo-acquisition.service",
        "leo-acquisition-soak.service",
        "leo-worker@.service",
        "leo-api.service",
        "leo-reconcile.service",
        "leo-reconcile.timer",
        "leo-retention.service",
        "leo-retention.timer",
        "leo-qualification.service",
        "leo-qualification.timer",
    }

    assert expected.issubset(path.name for path in UNIT_ROOT.iterdir())


def test_systemd_analyze_accepts_every_template() -> None:
    executable = shutil.which("systemd-analyze")
    assert executable is not None, "systemd-analyze is required for deployment validation"
    units = tuple(str(path) for path in sorted(UNIT_ROOT.glob("leo-*.*")))
    result = subprocess.run(
        (executable, "verify", *units),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_units_use_installed_stable_entrypoints_and_current_commands() -> None:
    acquisition = _unit("leo-acquisition.service")["Service"]
    worker = _unit("leo-worker@.service")["Service"]
    reconcile = _unit("leo-reconcile.service")["Service"]
    retention = _unit("leo-retention.service")["Service"]
    qualification = _unit("leo-qualification.service")["Service"]
    soak = _unit("leo-acquisition-soak.service")["Service"]
    api = _unit("leo-api.service")["Service"]

    assert acquisition["ExecStart"].endswith("leo acquire run --profile ${LEO_CAPTURE_PROFILE}")
    assert "leo process worker --worker-id worker-%i" in worker["ExecStart"]
    assert reconcile["ExecStart"].endswith("leo process reconcile --json")
    assert retention["ExecStart"].endswith("leo process retention-run --execute --automatic --json")
    assert (
        "leo acquire qualify --profile ${LEO_QUALIFICATION_PROFILE}" in qualification["ExecStart"]
    )
    assert "leo acquire soak --profile ${LEO_SOAK_PROFILE}" in soak["ExecStart"]
    assert "--duration-seconds ${LEO_SOAK_DURATION_SECONDS}" in soak["ExecStart"]
    assert api["ExecStart"] == "/usr/bin/env leo-api"
    assert "uvicorn" not in api["ExecStart"]


def test_every_systemd_cli_command_exists_in_the_real_inventory() -> None:
    root = get_command(create_cli())
    assert isinstance(root, TyperGroup)
    acquire = root.commands["acquire"]
    process = root.commands["process"]
    assert isinstance(acquire, TyperGroup)
    assert isinstance(process, TyperGroup)
    assert {"run", "qualify", "soak"} <= acquire.commands.keys()
    assert {"worker", "reconcile", "retention-run"} <= process.commands.keys()

    retention = process.commands["retention-run"]
    automatic = next(
        parameter
        for parameter in retention.params
        if "--automatic" in getattr(parameter, "opts", ())
    )
    assert getattr(automatic, "hidden", False)


def test_acquisition_is_prioritized_over_workers_and_maintenance() -> None:
    acquisition = _unit("leo-acquisition.service")["Service"]
    worker = _unit("leo-worker@.service")["Service"]
    retention = _unit("leo-retention.service")["Service"]

    assert int(acquisition["CPUWeight"]) > int(worker["CPUWeight"])
    assert int(acquisition["IOWeight"]) > int(worker["IOWeight"])
    assert int(acquisition["Nice"]) < int(worker["Nice"])
    assert int(worker["CPUWeight"]) > int(retention["CPUWeight"])
    assert worker["IOSchedulingClass"] == "idle"
    assert retention["IOSchedulingClass"] == "idle"
    assert int(acquisition["OOMScoreAdjust"]) < int(worker["OOMScoreAdjust"])


def test_retention_is_explicitly_gated_and_timers_are_persistent() -> None:
    retention_unit = _unit("leo-retention.service")["Unit"]
    retention_timer = _unit("leo-retention.timer")["Timer"]
    reconcile_timer = _unit("leo-reconcile.timer")["Timer"]
    qualification_unit = _unit("leo-qualification.service")["Unit"]
    soak_unit = _unit("leo-acquisition-soak.service")["Unit"]
    qualification_timer = _unit("leo-qualification.timer")["Timer"]

    assert retention_unit["ConditionPathExists"] == "/etc/leo/retention-enabled"
    assert qualification_unit["ConditionPathExists"] == "/etc/leo/qualification-enabled"
    assert soak_unit["ConditionPathExists"] == "/etc/leo/soak-enabled"
    assert retention_timer.getboolean("Persistent")
    assert retention_timer["Unit"] == "leo-retention.service"
    assert reconcile_timer.getboolean("Persistent")
    assert reconcile_timer["Unit"] == "leo-reconcile.service"
    assert qualification_timer.getboolean("Persistent")
    assert "UTC" in qualification_timer["OnCalendar"]


def test_api_is_open_lan_read_only_and_services_fail_closed_without_env() -> None:
    api = _unit("leo-api.service")
    assert "read-only LAN" in api["Unit"]["Description"]
    assert api["Service"]["ReadOnlyPaths"] == "/srv/bulk/leo"

    production_source = (PROJECT_ROOT / "src" / "leo" / "api" / "production.py").read_text()
    assert 'host: str = "0.0.0.0"' in production_source

    for path in _services():
        service = _unit(path.name)["Service"]
        assert service["EnvironmentFile"] == "/etc/leo/leo.env"
        assert service["NoNewPrivileges"] == "yes"
        assert service["ProtectSystem"] == "strict"
        assert service["RestrictSUIDSGID"] == "yes"


def test_environment_example_is_parseable_non_secret_and_complete() -> None:
    values: dict[str, str] = {}
    for raw_line in ENV_EXAMPLE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip("'")

    assert {
        "LEO_BULK_ROOT",
        "LEO_PROFILE_ROOT",
        "LEO_WEB_DIST",
        "LEO_CORPUS_ROOT",
        "LEO_DATABASE_URL",
        "LEO_RADIO_BACKEND",
        "LEO_RADIOS_JSON",
        "LEO_CAPTURE_PROFILE",
        "LEO_ACQUISITION_RESERVE_BYTES",
        "LEO_PIPELINE_RELEASE_ID",
        "LEO_WORKER_POLL_SECONDS",
        "LEO_API_PORT",
        "LEO_QUALIFICATION_PROFILE",
        "LEO_QUALIFICATION_TRIALS",
        "LEO_QUALIFICATION_RECEIPT",
        "LEO_SOAK_PROFILE",
        "LEO_SOAK_DURATION_SECONDS",
        "LEO_SOAK_CADENCE_SECONDS",
        "LEO_SOAK_ID",
        "LEO_SOAK_OUTPUT_ROOT",
    } <= values.keys()
    assert values["LEO_BULK_ROOT"] == "/srv/bulk/leo"
    assert values["LEO_DATABASE_URL"] == "postgresql+psycopg:///leo_tracker"
    assert values["LEO_RADIO_BACKEND"] == "pluto"
    radios = json.loads(values["LEO_RADIOS_JSON"])
    assert len(radios) == 2
    assert {item["receiver_count"] for item in radios} == {2}
    assert {item["serial"] for item in radios} == {"REPLACE-A", "REPLACE-B"}
    assert values["LEO_CORPUS_ROOT"].startswith("/srv/bulk/leo/")
    assert values["LEO_WEB_DIST"] == "/opt/leo-tracker/web/dist"
    assert "password" not in values["LEO_DATABASE_URL"].casefold()
    assert not values["LEO_BULK_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_CORPUS_ROOT"].startswith("/mnt/qnap01")
    assert values["LEO_SOAK_DURATION_SECONDS"] == "86400"
    assert values["LEO_SOAK_OUTPUT_ROOT"].startswith("/srv/bulk/leo/")
    assert not values["LEO_SOAK_OUTPUT_ROOT"].startswith("/mnt/qnap01")


def test_runbook_covers_required_operator_and_safety_topics() -> None:
    document = RUNBOOK.read_text().casefold()
    required_phrases = (
        "alembic",
        "doctor --probe-radios",
        "leo acquire once",
        "leo process reconcile",
        "leo process reprocess",
        "import-qnap",
        "leo process pin",
        "leo process unpin",
        "70%",
        "retention-run --dry-run",
        "--execute --automatic",
        "pg_dump",
        "pg_restore",
        "filesystem outage",
        "database outage",
        "restart order",
        "journalctl",
        "24-hour",
        "raid was rebuilding",
        "rerun",
        "/mnt/qnap01",
        "never delete, move, rename",
    )
    assert all(phrase in document for phrase in required_phrases)
