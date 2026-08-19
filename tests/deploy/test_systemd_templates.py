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
RELEASE_RUNBOOK = PROJECT_ROOT / "docs" / "operations" / "release-qualification.md"
DEPLOYMENT_RUNBOOK = PROJECT_ROOT / "docs" / "operations" / "production-deployment.md"
STAGE_SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "stage-production-release"
STAGE_CHECKER = PROJECT_ROOT / "deploy" / "scripts" / "check-staged-release"
CLEANUP_SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "remove-unpublished-release"
PUBLISHED_VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-published-release"
METADATA_VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-release-metadata"
CURRENT_VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-current-release"
CUTOVER_VERIFIER = PROJECT_ROOT / "deploy" / "scripts" / "verify-production-cutover"


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

    assert acquisition["ExecStart"].endswith(
        "/.venv/bin/leo acquire run --profile ${LEO_CAPTURE_PROFILE}"
    )
    assert "leo process worker --worker-id worker-%i" in worker["ExecStart"]
    assert reconcile["ExecStart"].endswith("leo process reconcile --json")
    assert retention["ExecStart"].endswith("leo process retention-run --execute --automatic --json")
    assert (
        "leo acquire qualify --profile ${LEO_QUALIFICATION_PROFILE}" in qualification["ExecStart"]
    )
    assert "leo acquire soak --profile ${LEO_SOAK_PROFILE}" in soak["ExecStart"]
    assert "--duration-seconds ${LEO_SOAK_DURATION_SECONDS}" in soak["ExecStart"]
    assert api["ExecStart"] == "/usr/bin/env /opt/leo-tracker/current/.venv/bin/leo-api"
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
    assert acquisition["OOMScoreAdjust"] == "200"
    assert worker["OOMScoreAdjust"] == "500"
    api = _unit("leo-api.service")["Service"]
    assert api["CPUWeight"] == "200"
    assert api["IOWeight"] == "200"
    assert api["OOMScoreAdjust"] == "400"


def test_every_service_uses_immutable_release_and_denies_qnap() -> None:
    for path in _services():
        service = _unit(path.name)["Service"]
        assert service["WorkingDirectory"] == "/opt/leo-tracker/current"
        assert service["InaccessiblePaths"] == "/mnt/qnap01"
        assert "/home/" not in service["ExecStart"]
        assert "/opt/leo-tracker/current/" in service["ExecStart"]


def test_retention_is_explicitly_gated_and_timers_are_persistent() -> None:
    retention_unit = _unit("leo-retention.service")["Unit"]
    retention_timer = _unit("leo-retention.timer")["Timer"]
    reconcile_timer = _unit("leo-reconcile.timer")["Timer"]
    qualification_unit = _unit("leo-qualification.service")["Unit"]
    soak_unit = _unit("leo-acquisition-soak.service")["Unit"]
    qualification_timer = _unit("leo-qualification.timer")["Timer"]
    release_unit = _unit("leo-release-qualification.service")["Unit"]
    release_timer = _unit("leo-release-qualification.timer")["Timer"]

    assert retention_unit["ConditionPathExists"] == "/etc/leo/retention-enabled"
    assert qualification_unit["ConditionPathExists"] == "/etc/leo/qualification-enabled"
    assert soak_unit["ConditionPathExists"] == "/etc/leo/soak-enabled"
    assert release_unit["ConditionPathExists"] == "/etc/leo/release-qualification-enabled"
    assert retention_timer.getboolean("Persistent")
    assert retention_timer["Unit"] == "leo-retention.service"
    assert reconcile_timer.getboolean("Persistent")
    assert reconcile_timer["Unit"] == "leo-reconcile.service"
    assert qualification_timer.getboolean("Persistent")
    assert "UTC" in qualification_timer["OnCalendar"]
    assert release_timer.getboolean("Persistent")
    assert release_timer["Unit"] == "leo-release-qualification.service"


def test_release_qualification_is_isolated_from_production_and_qnap() -> None:
    service = _unit("leo-release-qualification.service")["Service"]

    assert service["InaccessiblePaths"] == "/mnt/qnap01"
    assert service["ReadOnlyPaths"] == "/srv/bulk/leo/test-corpus"
    assert service["ReadWritePaths"] == "/srv/bulk/leo/qualification/release"
    assert "leo-release-qualify" in service["ExecStart"]
    assert "leo-acquisition" not in service.get("Conflicts", "")
    assert service["IOSchedulingClass"] == "idle"
    unit_text = (UNIT_ROOT / "leo-release-qualification.service").read_text()
    assert "PATH=/opt/leo-tracker/tooling:" in unit_text
    assert "PLAYWRIGHT_BROWSERS_PATH=/var/lib/leo/.cache/ms-playwright" in unit_text
    assert "GIT_CONFIG_KEY_0=safe.directory" in unit_text
    assert "GIT_CONFIG_VALUE_0=/opt/leo-tracker/current" in unit_text
    assert "ExecStartPre=" in unit_text
    assert "validate-current-release /opt/leo-tracker/current" in unit_text
    release_runbook = RELEASE_RUNBOOK.read_text()
    assert "PATH=/opt/leo-tracker/tooling:" in release_runbook
    assert "PLAYWRIGHT_BROWSERS_PATH" in release_runbook


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
        "LEO_QUALIFICATION_DATABASE_URL",
        "LEO_QUALIFICATION_CORPUS_ROOT",
        "LEO_RELEASE_QUALIFICATION_ROOT",
        "PLAYWRIGHT_BROWSERS_PATH",
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
    assert values["LEO_QUALIFICATION_DATABASE_URL"] == ("postgresql+psycopg:///leo_qualification")
    assert values["PLAYWRIGHT_BROWSERS_PATH"] == "/var/lib/leo/.cache/ms-playwright"
    assert values["LEO_RADIO_BACKEND"] == "pluto"
    radios = json.loads(values["LEO_RADIOS_JSON"])
    assert len(radios) == 2
    assert {item["receiver_count"] for item in radios} == {2}
    assert {item["serial"] for item in radios} == {"REPLACE-A", "REPLACE-B"}
    assert values["LEO_CORPUS_ROOT"].startswith("/srv/bulk/leo/")
    assert values["LEO_PROFILE_ROOT"] == "/opt/leo-tracker/current/profiles"
    assert values["LEO_WEB_DIST"] == "/opt/leo-tracker/current/web/dist"
    assert "password" not in values["LEO_DATABASE_URL"].casefold()
    assert not values["LEO_BULK_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_CORPUS_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_QUALIFICATION_CORPUS_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_RELEASE_QUALIFICATION_ROOT"].startswith("/mnt/qnap01")
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


def test_production_deployment_is_staged_guarded_and_data_safe() -> None:
    document = DEPLOYMENT_RUNBOOK.read_text().casefold()
    required_phrases = (
        "immutable production deployment",
        "terminal soak acceptance",
        "exact staged sha",
        "pre-cutover",
        "reassign owned by mouse9911 to leo",
        "directory-only acl pass",
        "-xdev",
        "alembic upgrade head",
        "cutover preflight passed",
        "leo-worker@{1..8}.service",
        "oomscoreadjust",
        "two fully committed continuous dwells",
        "rollback without data loss",
        "never run `alembic downgrade`",
        "post-resync",
        "/mnt/qnap01",
    )
    assert all(phrase in document for phrase in required_phrases)

    assert STAGE_SCRIPT.stat().st_mode & 0o111
    assert STAGE_CHECKER.stat().st_mode & 0o111
    assert CLEANUP_SCRIPT.stat().st_mode & 0o111
    assert PUBLISHED_VALIDATOR.stat().st_mode & 0o111
    assert METADATA_VALIDATOR.stat().st_mode & 0o111
    assert CURRENT_VALIDATOR.stat().st_mode & 0o111
    assert CUTOVER_VERIFIER.stat().st_mode & 0o111
    stage = STAGE_SCRIPT.read_text()
    assert "--revision FULL_40_HEX_SHA" in stage
    assert "--execute" in stage
    assert "/srv/bulk" not in stage
    assert "systemctl" not in stage
    assert "psql" not in stage
    assert "current.next" not in stage
    assert "install -d -o leo -g leo -m 0750 /var/lib/leo/.cache" in stage
    assert "/var/lib/leo/.cache/uv /var/lib/leo/.cache/ms-playwright" in stage
    assert "PLAYWRIGHT_BROWSERS_PATH=/var/lib/leo/.cache/ms-playwright" in stage
    assert stage.index("trap cleanup EXIT") < stage.index("git clone")
    assert 'rm -rf --one-file-system -- "$staging_dir"' in stage
    assert 'mv -- "$staging_dir" "$release_dir"' in stage
    assert stage.index('mv -- "$staging_dir" "$release_dir"') < stage.index(
        '/opt/leo-tracker/tooling/uv --directory "$release_dir"'
    )
    assert '--directory "$release_dir" sync --frozen' in stage
    assert "--no-editable" in stage
    assert 'runuser -u leo -- "$release_dir/deploy/scripts/check-staged-release"' in stage
    assert '"$release_dir/deploy/scripts/validate-published-release"' in stage
    metadata_publish = stage.index('mv -- "$metadata_temp" "$metadata"')
    assert stage.rindex("validate-published-release") < metadata_publish
    assert stage.index('rm -f -- "$release_dir/.leo-release-incomplete"') < metadata_publish
    assert "mktemp" in stage
    assert "flock -n 9" in stage
    assert ".leo-release-incomplete" in stage
    assert '"$script_root/remove-unpublished-release"' in stage
    assert "[[ -z $(git" not in stage
    assert "[[ $(git" not in stage
    assert "invalid-cleanliness-check" in document
    verifier = CUTOVER_VERIFIER.read_text()
    assert "CUTOVER BLOCKED" in verifier
    assert "InaccessiblePaths=/mnt/qnap01" in verifier
    assert "validate-release-metadata" in verifier
    assert "validate-published-release" in verifier
    qualification_source = (PROJECT_ROOT / "src/leo/qualification/release.py").read_text()
    assert "_validate_deployed_release(project_root, revision)" in qualification_source


def test_release_stage_dry_run_is_non_mutating_and_pins_exact_head() -> None:
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    result = subprocess.run(
        (str(STAGE_SCRIPT), "--source", str(PROJECT_ROOT), "--revision", revision),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert revision in result.stdout
    assert "without changing services, data, or PostgreSQL" in result.stdout


def test_cutover_verifier_fails_before_host_access_for_non_exact_revision() -> None:
    result = subprocess.run(
        (
            str(CUTOVER_VERIFIER),
            "--revision",
            "not-a-revision",
            "--legacy-user",
            "mouse9911",
            "--release-receipt",
            "/does/not/exist",
            "--soak-receipt",
            "/does/not/exist",
        ),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "CUTOVER BLOCKED" in result.stderr
    assert "full lowercase 40-character SHA" in result.stderr
