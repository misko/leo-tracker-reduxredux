from __future__ import annotations

import configparser
import json
import shlex
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
CACHE_PREPARER = PROJECT_ROOT / "deploy" / "scripts" / "prepare-leo-cache"
CUTOVER_VERIFIER = PROJECT_ROOT / "deploy" / "scripts" / "verify-production-cutover"
FAST_API_RESTART = PROJECT_ROOT / "deploy" / "scripts" / "restart-current-api"
COMPONENT_SELECTOR = PROJECT_ROOT / "deploy" / "scripts" / "select-component-release"


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


def test_fast_api_restart_is_narrow_and_syntax_valid() -> None:
    text = FAST_API_RESTART.read_text()

    assert FAST_API_RESTART.stat().st_mode & 0o111
    assert "/usr/bin/systemctl restart leo-api.service" in text
    assert "http://127.0.0.1:8090/api/v1/status" in text
    assert "releases/([0-9a-f]{40})" in text
    assert "root:leo:440" in text
    for forbidden in (
        "stage-production-release",
        "verify-production-cutover",
        "leo-release-qualify",
        "alembic",
        "leo-worker@",
        "leo-acquisition.service",
        "leo-reconcile.service",
    ):
        assert forbidden not in text
    subprocess.run(("/usr/bin/bash", "-n", str(FAST_API_RESTART)), check=True)


def test_component_selector_is_atomic_bounded_and_syntax_valid() -> None:
    text = COMPONENT_SELECTOR.read_text()

    assert COMPONENT_SELECTOR.stat().st_mode & 0o111
    assert "^(api|worker|acquisition|global)$" in text
    assert "releases/$revision" in text
    assert "mv -Tf" in text
    assert "rm -rf" not in text
    assert "/mnt/qnap01" not in text
    subprocess.run(("/usr/bin/bash", "-n", str(COMPONENT_SELECTOR)), check=True)


def test_systemd_analyze_accepts_every_template() -> None:
    executable = shutil.which("systemd-analyze")
    assert executable is not None, "systemd-analyze is required for deployment validation"
    units = tuple(str(path) for path in sorted(UNIT_ROOT.glob("leo-*.*")) if path.is_file())
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
        "/.venv/bin/leo acquire run --profile ${LEO_CAPTURE_PROFILE} "
        "--profile ${LEO_CAPTURE_PROFILE_5M} "
        "--radio radio_pluto_5d4d --radio radio_pluto_19f2 "
        "--interval-seconds ${LEO_CAPTURE_INTERVAL_SECONDS} "
        "--mixed-rate-policy ${LEO_MIXED_RATE_POLICY}"
    )
    assert "leo process worker --worker-id worker-%i" in worker["ExecStart"]
    assert reconcile["ExecStart"].endswith("leo process reconcile --json")
    assert retention["ExecStart"].endswith("leo process retention-run --execute --automatic --json")
    assert (
        "leo acquire qualify --profile ${LEO_QUALIFICATION_PROFILE}" in qualification["ExecStart"]
    )
    assert "leo acquire soak --profile ${LEO_SOAK_PROFILE}" in soak["ExecStart"]
    assert "--duration-seconds ${LEO_SOAK_DURATION_SECONDS}" in soak["ExecStart"]
    assert api["ExecStart"] == (
        "/usr/bin/env PYTHONDONTWRITEBYTECODE=1 "
        "LEO_WEB_DIST=/opt/leo-tracker/current-api/web/dist "
        "/opt/leo-tracker/current-api/.venv/bin/leo-api"
    )
    assert "uvicorn" not in api["ExecStart"]


def test_every_python_service_forces_bytecode_suppression_at_exec_boundary() -> None:
    services = _services()

    assert services
    for path in services:
        text = path.read_text()
        service = _unit(path.name)["Service"]
        command = shlex.split(service["ExecStart"])
        executable_index = next(
            index for index, argument in enumerate(command) if "/.venv/bin/" in argument
        )
        assert service["EnvironmentFile"] == "/etc/leo/leo.env"
        assert command[0] == "/usr/bin/env"
        assert command.count("PYTHONDONTWRITEBYTECODE=1") == 1
        assert command.index("PYTHONDONTWRITEBYTECODE=1") < executable_index
        assert "Environment=PYTHONDONTWRITEBYTECODE=" not in text


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
    assert api["ReadWritePaths"] == "/srv/bulk/leo/control"


def test_worker_allows_ten_numerical_threads_at_the_exec_boundary() -> None:
    worker_text = (UNIT_ROOT / "leo-worker@.service").read_text()
    worker = _unit("leo-worker@.service")["Service"]
    command = shlex.split(worker["ExecStart"])
    executable_index = next(
        index for index, argument in enumerate(command) if "/.venv/bin/" in argument
    )

    for assignment in (
        "OPENBLAS_NUM_THREADS=10",
        "OMP_NUM_THREADS=10",
        "MKL_NUM_THREADS=10",
    ):
        assert command.count(assignment) == 1
        assert command.index(assignment) < executable_index
    assert "Environment=OPENBLAS_NUM_THREADS=" not in worker_text
    assert "Environment=OMP_NUM_THREADS=" not in worker_text
    assert "Environment=MKL_NUM_THREADS=" not in worker_text
    assert "Environment=MPLCONFIGDIR=/srv/bulk/leo/presentation-cache/matplotlib" in worker_text


def test_full_reconcile_is_asynchronous_to_runtime_startup() -> None:
    reconcile = _unit("leo-reconcile.service")["Unit"]
    for service_name in (
        "leo-api.service",
        "leo-acquisition.service",
        "leo-worker@.service",
    ):
        unit = _unit(service_name)["Unit"]
        assert "leo-reconcile.service" not in unit.get("After", "")
        assert "leo-reconcile.service" not in unit.get("Wants", "")
        assert "leo-reconcile.service" not in unit.get("Requires", "")
    assert "leo-acquisition.service" not in reconcile.get("Before", "")
    assert "leo-worker@.service" not in reconcile.get("Before", "")


def test_every_service_uses_immutable_release_and_denies_qnap() -> None:
    selectors = {
        "leo-api.service": "current-api",
        "leo-worker@.service": "current-worker",
        "leo-acquisition.service": "current-acquisition",
    }
    for path in _services():
        service = _unit(path.name)["Service"]
        selector = selectors.get(path.name, "current")
        assert service["WorkingDirectory"] == f"/opt/leo-tracker/{selector}"
        assert service["InaccessiblePaths"] == "/mnt/qnap01"
        assert "/home/" not in service["ExecStart"]
        assert f"/opt/leo-tracker/{selector}/" in service["ExecStart"]


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


def test_scanner_is_scheduled_by_the_capture_supervisor() -> None:
    acquisition = _unit("leo-acquisition.service")
    readme = (UNIT_ROOT / "README.md").read_text()

    assert "acquisition and scanner supervisor" in acquisition["Unit"]["Description"]
    assert "leo acquire run" in acquisition["Service"]["ExecStart"]
    assert not (UNIT_ROOT / "leo-scanner.service").exists()
    assert not (UNIT_ROOT / "leo-scanner.timer").exists()
    assert not (PROJECT_ROOT / "deploy/scripts/run-periodic-starlink-scan").exists()
    assert "per-radio leases" in readme
    assert "leo acquire pause" in readme


def test_release_qualification_is_isolated_from_production_and_qnap() -> None:
    service = _unit("leo-release-qualification.service")["Service"]

    assert service["InaccessiblePaths"] == "/mnt/qnap01"
    assert service["ReadOnlyPaths"] == "/srv/bulk/leo/test-corpus"
    assert service["ReadWritePaths"] == "/srv/bulk/leo/qualification/release"
    assert "leo-release-qualify" in service["ExecStart"]
    assert "leo-acquisition" not in service.get("Conflicts", "")
    assert service["IOSchedulingClass"] == "idle"
    unit_text = (UNIT_ROOT / "leo-release-qualification.service").read_text()
    assert "PATH=/opt/leo-tracker/current/.release-tools:" in unit_text
    assert "PLAYWRIGHT_BROWSERS_PATH=/var/lib/leo/.cache/ms-playwright" in unit_text
    assert "GIT_CONFIG_KEY_0=safe.directory" in unit_text
    assert "GIT_CONFIG_VALUE_0=/opt/leo-tracker/current" in unit_text
    assert "ExecStartPre=" in unit_text
    assert "validate-current-release /opt/leo-tracker/current" in unit_text
    release_runbook = RELEASE_RUNBOOK.read_text()
    assert "PATH=/opt/leo-tracker/current/.release-tools:" in release_runbook
    assert "PLAYWRIGHT_BROWSERS_PATH" in release_runbook
    assert ".release-tools/" in (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    playwright = (PROJECT_ROOT / "web/playwright.config.ts").read_text()
    assert "uv run --frozen --no-sync uvicorn" in playwright


def test_api_is_open_lan_read_only_and_services_fail_closed_without_env() -> None:
    api = _unit("leo-api.service")
    assert "read-only LAN" in api["Unit"]["Description"]
    assert api["Service"]["ReadOnlyPaths"] == "/srv/bulk/leo"
    assert api["Service"]["ReadWritePaths"] == "/srv/bulk/leo/control"

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
        "LEO_QUALIFICATION_ROOT",
        "LEO_CAPTURE_EVIDENCE_ROOT",
        "LEO_LEGACY_EVIDENCE_ROOT",
        "LEO_QUALIFICATION_DATABASE_URL",
        "LEO_QUALIFICATION_CORPUS_ROOT",
        "LEO_RELEASE_QUALIFICATION_ROOT",
        "PLAYWRIGHT_BROWSERS_PATH",
        "LEO_RADIO_BACKEND",
        "LEO_RADIOS_JSON",
        "LEO_CAPTURE_PROFILE",
        "LEO_CAPTURE_PROFILE_5M",
        "LEO_MIXED_RATE_POLICY",
        "LEO_DIRECT_ASYNC_ENABLED",
        "LEO_CAPTURE_INTERVAL_SECONDS",
        "LEO_ACQUISITION_RESERVE_BYTES",
        "LEO_SCANNER_ENABLED",
        "LEO_SCANNER_RADIO_ID",
        "LEO_SCANNER_INTERVAL_SECONDS",
        "LEO_SCANNER_MAXIMUM_LATENESS_SECONDS",
        "LEO_SCANNER_DWELL_MS",
        "LEO_SCANNER_GAIN_DB",
        "LEO_SCANNER_MARGIN_GATE",
        "LEO_SCANNER_REPORT_ROOT",
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
    assert values["LEO_QUALIFICATION_ROOT"] == "/srv/bulk/leo/qualification"
    assert values["LEO_CAPTURE_EVIDENCE_ROOT"] == "/srv/bulk/leo/qualification/capture"
    assert values["LEO_LEGACY_EVIDENCE_ROOT"] == "/srv/bulk/leo/qualification/legacy"
    assert values["LEO_DATABASE_URL"] == "postgresql+psycopg:///leo_tracker"
    assert values["LEO_QUALIFICATION_DATABASE_URL"] == ("postgresql+psycopg:///leo_qualification")
    assert values["PLAYWRIGHT_BROWSERS_PATH"] == "/var/lib/leo/.cache/ms-playwright"
    assert values["LEO_RADIO_BACKEND"] == "pluto"
    radios = json.loads(values["LEO_RADIOS_JSON"])
    assert len(radios) == 2
    assert {item["receiver_count"] for item in radios} == {2}
    assert {item["radio_id"] for item in radios} == {
        "radio_pluto_5d4d",
        "radio_pluto_19f2",
    }
    assert {item["serial"] for item in radios} == {
        "1040005e0b100007100010000bf33a5d4d",
        "10400056f695001322002d0010ad1719f2",
    }
    assert {item["host"] for item in radios} == {"192.168.1.20", "192.168.1.21"}
    assert values["LEO_PIPELINE_RELEASE_ID"] == "REPLACE-PIPELINE-RELEASE-ID"
    assert values["LEO_CAPTURE_PROFILE"] == "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4"
    assert values["LEO_CAPTURE_PROFILE_5M"] == "starlink-ch4-lower-5m-60s-native-bandwidth-v4"
    assert values["LEO_MIXED_RATE_POLICY"] == (
        "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2"
    )
    assert values["LEO_DIRECT_ASYNC_ENABLED"] == "true"
    assert values["LEO_QUALIFICATION_PROFILE"] == (
        "starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2"
    )
    assert values["LEO_SOAK_PROFILE"] == "starlink-ch4-lower-2p5m-60s-continuity-v2"
    assert values["LEO_CAPTURE_INTERVAL_SECONDS"] == "180"
    assert values["LEO_SCANNER_ENABLED"] == "true"
    assert values["LEO_SCANNER_RADIO_ID"] == "radio_pluto_5d4d"
    assert values["LEO_SCANNER_INTERVAL_SECONDS"] == "180"
    assert values["LEO_CORPUS_ROOT"].startswith("/srv/bulk/leo/")
    assert values["LEO_PROFILE_ROOT"] == "/opt/leo-tracker/current/profiles"
    assert values["LEO_WEB_DIST"] == "/opt/leo-tracker/current/web/dist"
    assert "password" not in values["LEO_DATABASE_URL"].casefold()
    assert not values["LEO_BULK_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_CORPUS_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_QUALIFICATION_CORPUS_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_RELEASE_QUALIFICATION_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_QUALIFICATION_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_CAPTURE_EVIDENCE_ROOT"].startswith("/mnt/qnap01")
    assert not values["LEO_LEGACY_EVIDENCE_ROOT"].startswith("/mnt/qnap01")
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
    deployment_text = DEPLOYMENT_RUNBOOK.read_text()
    document = deployment_text.casefold()
    required_phrases = (
        "immutable production deployment and lean standard cutover",
        "reviewed four-path standard receipt",
        "24-hour soak",
        "not a prerequisite",
        "staged sha",
        "pre-cutover",
        "reassign owned by mouse9911 to leo",
        "directory-only acl pass",
        "-xdev",
        "alembic upgrade head",
        "cutover preflight passed",
        "leo-worker@{1..20}.service",
        "oomscoreadjust",
        "two short observations",
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
    assert CACHE_PREPARER.stat().st_mode & 0o111
    assert CUTOVER_VERIFIER.stat().st_mode & 0o111
    stage = STAGE_SCRIPT.read_text()
    assert "--revision FULL_40_HEX_SHA" in stage
    assert "--execute" in stage
    assert "/srv/bulk" not in stage
    assert "systemctl" not in stage
    assert "psql" not in stage
    assert "current.next" not in stage
    assert '"$script_root/prepare-leo-cache"' in stage
    assert "PLAYWRIGHT_BROWSERS_PATH=/var/lib/leo/.cache/ms-playwright" in stage
    assert stage.index("trap cleanup EXIT") < stage.index("git clone")
    assert 'rm -rf --one-file-system -- "$staging_dir"' in stage
    assert 'mv -- "$staging_dir" "$release_dir"' in stage
    assert stage.index('mv -- "$staging_dir" "$release_dir"') < stage.index(
        '"$release_uv" --directory "$release_dir"'
    )
    assert "--python-bin ABSOLUTE_VERSIONED_SYSTEM_PYTHON" in stage
    assert '--python "$python_bin"' in stage
    assert "python_version=" in stage
    assert "printf 'python=%s" in stage
    assert "release_uv=$release_dir/.release-tools/uv" in stage
    assert 'sha256sum "$python_bin" "$release_uv"' in stage
    assert '--directory "$release_dir" sync --frozen' in stage
    assert "--no-editable" in stage
    assert '"$release_dir/.venv/bin/pluto-install-metadata-runtime"' in stage
    assert '--metadata-abi "$metadata_abi"' in stage
    assert "metadata_abi=3" in stage
    assert stage.index('--directory "$release_dir" sync --frozen') < stage.index(
        '"$release_dir/.venv/bin/pluto-install-metadata-runtime"'
    )
    compile_bytecode = stage.index('"$release_dir/.venv/bin/python" -m compileall')
    assert stage.index('"$release_dir/.venv/bin/pluto-install-metadata-runtime"') < (
        compile_bytecode
    )
    assert compile_bytecode < stage.index('chown -R root:leo "$release_dir"')
    assert "-q -f --invalidation-mode checked-hash" in stage
    assert '"$release_dir/.venv/lib/python$python_version/site-packages"' in stage
    assert "metadata-runtime.json" in stage
    assert '"${metadata_runtime_paths[@]}"' in stage
    assert 'runuser -u leo -- "$release_dir/deploy/scripts/check-staged-release"' in stage
    assert '"$release_dir/deploy/scripts/validate-published-release"' in stage
    metadata_publish = stage.index('mv -- "$metadata_temp" "$metadata"')
    assert stage.rindex("validate-published-release") < metadata_publish
    assert stage.index('rm -f -- "$release_dir/.leo-release-incomplete"') < metadata_publish
    assert stage.count('PYTHONDONTWRITEBYTECODE=1 "$release_dir/.venv/bin/python"') == 2
    assert "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2" in deployment_text
    assert 'sudo ./ops deploy --full --revision "$release_revision"' in deployment_text
    assert "public.processing_resource_capacity" in deployment_text
    assert "streaming=16`, `cpu=8`,\n`memory=4`, and `heavy=2" in deployment_text
    assert deployment_text.count("leo acquire resume --operator production-cutover") == 2
    assert deployment_text.count("leo acquire pause --operator production-cutover") >= 2
    assert 'leo acquire once --profile "$LEO_CAPTURE_PROFILE" --json' in deployment_text
    assert 'leo acquire once --profile "$LEO_CAPTURE_PROFILE_5M" --json' in deployment_text
    assert "Continuous acquisition requires a later, separate\noperator resume" in deployment_text
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
    python_bin = next(
        path
        for minor in (14, 13, 12)
        if (path := Path(f"/usr/bin/python3.{minor}")).is_file() and not path.is_symlink()
    )
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    result = subprocess.run(
        (
            str(STAGE_SCRIPT),
            "--source",
            str(PROJECT_ROOT),
            "--revision",
            revision,
            "--python-bin",
            str(python_bin),
        ),
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


def test_staged_release_git_check_disables_optional_index_writes() -> None:
    assert "export GIT_OPTIONAL_LOCKS=0" in STAGE_CHECKER.read_text()
