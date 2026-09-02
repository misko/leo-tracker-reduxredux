from __future__ import annotations

import json
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest

from leo.qualification import release
from leo.qualification.release_contract import (
    RELEASE_QUALIFICATION_V1_SCHEMA,
    RELEASE_QUALIFICATION_V2_SCHEMA,
    RELEASE_QUALIFICATION_V3_COMMAND_NAMES,
    RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS,
    RELEASE_QUALIFICATION_V3_SCHEMA,
    release_qualification_schema_version,
    release_qualification_v3_command_documents,
    release_qualification_v3_lane_metadata,
    summarize_pytest_junit_v1,
    validate_reusable_release_qualification_v3_lane,
)


@pytest.fixture(autouse=True)
def _isolated_database_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release, "_qualification_schemas", lambda _url: ("public",))


def _project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    (project / "web").mkdir(parents=True)
    (project / "corpus").mkdir()
    (project / "uv.lock").write_text("locked-python\n")
    (project / "web" / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (project / "corpus" / "manifest.json").write_text('{"schema":"test"}\n')
    for relative_path in {
        path for paths in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS.values() for path in paths
    }:
        target = project / relative_path
        if target.exists():
            continue
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"fixture for {relative_path}\n")
        else:
            target.mkdir(parents=True, exist_ok=True)
    corpus = tmp_path / "protected-corpus"
    corpus.mkdir()
    evidence = tmp_path / "evidence"
    return project.resolve(), corpus.resolve(), evidence.resolve()


def _clean_git(_project: Path, *arguments: str) -> str:
    if arguments == ("rev-parse", "HEAD"):
        return "a" * 40
    if arguments == ("rev-parse", "HEAD^{tree}"):
        return "b" * 40
    return ""


def test_canonical_deployed_release_requires_external_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = "a" * 40
    deployment = tmp_path / "leo-tracker"
    project = deployment / "releases" / revision
    project.mkdir(parents=True)
    monkeypatch.setattr(release, "_DEPLOYMENT_ROOT", deployment)

    with pytest.raises(ValueError, match="no sealed external metadata"):
        release._validate_deployed_release(project, revision)


def test_canonical_deployed_release_propagates_bad_metadata_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = "b" * 40
    deployment = tmp_path / "leo-tracker"
    project = deployment / "releases" / revision
    metadata = deployment / "release-metadata" / f"{revision}.txt"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("bad metadata\n")
    required = (
        project / "deploy/scripts/validate-release-metadata",
        project / "deploy/scripts/validate-published-release",
        project / ".venv/bin/python",
    )
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 1\n")
        path.chmod(0o755)
    monkeypatch.setattr(release, "_DEPLOYMENT_ROOT", deployment)

    def fail_validation(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(release.subprocess, "run", fail_validation)
    with pytest.raises(subprocess.CalledProcessError):
        release._validate_deployed_release(project, revision)


def test_release_lane_seals_reproducible_pass_receipt_and_isolates_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)
    observed: list[tuple[str, dict[str, str]]] = []

    def execute(
        command: release.QualificationCommand,
        environment: dict[str, str],
        log_path: Path,
    ) -> int:
        observed.append((command.name, environment))
        log_path.write_text(f"{command.name} passed\n")
        junit_arguments = tuple(item for item in command.argv if item.startswith("--junitxml="))
        if junit_arguments:
            junit = next(Path(item.removeprefix("--junitxml=")) for item in junit_arguments)
            junit.write_text(
                "<testsuite tests='1' failures='0' errors='0' skipped='0'>"
                f"<testcase classname='qualification' name='{command.name}'/>"
                "</testsuite>\n"
            )
        if command.name == "production-web-build":
            output = Path(command.argv[-1])
            (output / "assets").mkdir(parents=True)
            (output / "index.html").write_text("<main>compiled</main>\n")
            (output / "assets" / "app.js").write_text("compiled();\n")
        return 0

    monkeypatch.setattr(release, "_git_output", _clean_git)
    monkeypatch.setattr(release, "_run_command", execute)
    monkeypatch.setenv("LEO_DATABASE_URL", "postgresql+psycopg:///leo_tracker")
    monkeypatch.setenv("LEO_BULK_ROOT", "/srv/bulk/leo")
    monkeypatch.setenv("LEO_WEB_DIST", "/opt/leo-tracker/web/dist")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-leak")
    monkeypatch.setenv("PYTHONPATH", "/must/not/leak")

    receipt_path = release.run_release_qualification(
        project_root=project,
        database_url="postgresql+psycopg:///leo_qualification",
        corpus_root=corpus,
        evidence_root=evidence,
        run_id="release-test-pass",
    )

    receipt = json.loads(receipt_path.read_bytes())
    definition = json.loads((receipt_path.parent / "definition.json").read_bytes())
    assert receipt["passed"] is True
    assert receipt["status"] == "passed"
    assert [item["name"] for item in receipt["commands"]] == list(
        RELEASE_QUALIFICATION_V3_COMMAND_NAMES
    )
    assert receipt["schema"] == RELEASE_QUALIFICATION_V3_SCHEMA
    assert definition["schema"] == RELEASE_QUALIFICATION_V3_SCHEMA
    assert definition["source"]["git_revision"] == "a" * 40
    assert definition["source"]["git_tree"] == "b" * 40
    assert definition["source"]["source_identity_kind"] == "clean-git-checkout"
    assert definition["commands"][0]["argv"][:4] == [
        "uv",
        "run",
        "--frozen",
        "--no-sync",
    ]
    qualification_argv = definition["commands"][0]["argv"]
    assert any("one_path_one_coarse_window" in item for item in qualification_argv)
    assert not any(
        "standard_v2_four_path_operational_vertical" in item for item in qualification_argv
    )
    assert not any("full_four_path_twice" in item for item in qualification_argv)
    assert definition["isolation"]["database"] == "postgresql+psycopg:///leo_qualification"
    assert definition["isolation"]["qnap_access"] == "forbidden"
    assert definition["isolation"]["native_rate_corpus_root"] == str(corpus)
    assert definition["commands"][1]["name"] == "current-native-science"
    assert (
        "tests/analysis/test_standard_native_scientific_equivalence.py"
        in (definition["commands"][1]["argv"])
    )
    assert definition["commands"][2]["name"] == "current-native-postgresql"
    assert any(
        "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical" in item
        for item in definition["commands"][2]["argv"]
    )
    build_argv = definition["commands"][3]["argv"]
    assert build_argv[:3] == ["npm", "--prefix", "$SCRATCH_ROOT/web"]
    assert build_argv[3:5] == ["run", "qualify:release"]
    assert any(item.startswith("$SCRATCH_ROOT/") for item in build_argv)
    assert not any("leo-release-qualification-" in item for item in build_argv)
    assert any(
        item["relative_path"] == "results/protected-real-corpus.junit.xml"
        for item in receipt["evidence"]
    )
    assert any(item["relative_path"] == "results/web-build.json" for item in receipt["evidence"])
    for _name, environment in observed:
        assert "LEO_DATABASE_URL" not in environment
        assert "LEO_BULK_ROOT" not in environment
        assert "LEO_WEB_DIST" not in environment
        assert "AWS_SECRET_ACCESS_KEY" not in environment
        assert "PYTHONPATH" not in environment
        assert Path(environment["HOME"]).name == "home"
        assert environment["HOME"] != str(Path.home())
        assert environment["LEO_TEST_DATABASE_URL"].endswith("/leo_qualification")
        assert environment["LEO_E2E_DATABASE_URL"].endswith("/leo_qualification")
        assert environment["LEO_REAL_CORPUS_ROOT"] == str(corpus)
        assert environment["LEO_NATIVE_REAL_CORPUS_ROOT"] == str(corpus)
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o440
    assert stat.S_IMODE(receipt_path.parent.stat().st_mode) == 0o550

    staged_dist = project / "web" / "dist"
    (staged_dist / "assets").mkdir(parents=True)
    (staged_dist / "index.html").write_text("<main>compiled</main>\n")
    (staged_dist / "assets" / "app.js").write_text("compiled();\n")
    observed.clear()

    def next_clean_git(_project: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "c" * 40
        if arguments == ("rev-parse", "HEAD^{tree}"):
            return "d" * 40
        return ""

    monkeypatch.setattr(release, "_git_output", next_clean_git)
    reused_receipt_path = release.run_release_qualification(
        project_root=project,
        database_url="postgresql+psycopg:///leo_qualification",
        corpus_root=corpus,
        evidence_root=evidence,
        run_id="release-test-reused",
    )
    reused_receipt = json.loads(reused_receipt_path.read_bytes())
    assert observed == []
    assert [item["name"] for item in reused_receipt["reused_lanes"]] == list(
        RELEASE_QUALIFICATION_V3_COMMAND_NAMES
    )
    assert reused_receipt["git_revision"] == "c" * 40
    assert reused_receipt["passed"] is True

    with pytest.raises(FileExistsError):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
            run_id="release-test-pass",
        )


def test_release_lane_records_parallel_failures_and_preserves_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)
    invoked: list[str] = []

    def fail_corpus(
        command: release.QualificationCommand,
        _environment: dict[str, str],
        log_path: Path,
    ) -> int:
        invoked.append(command.name)
        log_path.write_text("required fixture is missing\n")
        return 1

    monkeypatch.setattr(release, "_git_output", _clean_git)
    monkeypatch.setattr(release, "_run_command", fail_corpus)

    with pytest.raises(release.QualificationFailed) as failure:
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
            run_id="release-test-fail",
        )

    receipt = json.loads(failure.value.receipt_path.read_bytes())
    assert set(invoked) == {
        "protected-real-corpus",
        "current-native-science",
        "current-native-postgresql",
        "production-web-build",
    }
    assert receipt["status"] == "failed"
    assert receipt["passed"] is False
    assert receipt["commands"][0]["exit_code"] == 1
    assert receipt["commands"][-1]["exit_code"] == 70
    assert "blocked by failed lane dependencies" in receipt["commands"][-1]["validation_error"]


def test_release_lane_fails_closed_when_successful_command_omits_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)

    def omit_junit(
        _command: release.QualificationCommand,
        _environment: dict[str, str],
        log_path: Path,
    ) -> int:
        log_path.write_text("pytest claimed success without JUnit\n")
        return 0

    monkeypatch.setattr(release, "_git_output", _clean_git)
    monkeypatch.setattr(release, "_run_command", omit_junit)

    with pytest.raises(release.QualificationFailed) as failure:
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
            run_id="release-test-missing-junit",
        )

    receipt = json.loads(failure.value.receipt_path.read_bytes())
    assert receipt["commands"][0]["exit_code"] == 70
    assert "result evidence is invalid" in receipt["commands"][0]["validation_error"]
    assert (
        failure.value.receipt_path.parent / "results/protected-real-corpus.validation-error.txt"
    ).is_file()


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql+psycopg:///leo_tracker",
        "postgresql+psycopg:///research",
    ),
)
def test_release_lane_refuses_nonqualification_database(
    tmp_path: Path,
    database_url: str,
) -> None:
    project, corpus, evidence = _project(tmp_path)
    with pytest.raises(ValueError, match="qualification database name"):
        release.run_release_qualification(
            project_root=project,
            database_url=database_url,
            corpus_root=corpus,
            evidence_root=evidence,
        )


def test_release_lane_requires_postgresql(tmp_path: Path) -> None:
    project, corpus, evidence = _project(tmp_path)
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        release.run_release_qualification(
            project_root=project,
            database_url="sqlite:////tmp/leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
        )


def test_release_lane_rejects_database_with_preexisting_test_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)
    monkeypatch.setattr(
        release,
        "_qualification_schemas",
        lambda _url: ("leo_e2e_stale", "public"),
    )
    with pytest.raises(ValueError, match="must start with only the public schema"):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
        )


def test_release_lane_refuses_qnap_roots(tmp_path: Path) -> None:
    project, _corpus, evidence = _project(tmp_path)
    with pytest.raises(ValueError, match="cannot be beneath /mnt/qnap01"):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=Path("/mnt/qnap01"),
            evidence_root=evidence,
        )


def test_dirty_checkout_is_rejected_before_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)

    def dirty_git(_project: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        if arguments == ("rev-parse", "HEAD^{tree}"):
            return "b" * 40
        return " M source.py"

    monkeypatch.setattr(release, "_git_output", dirty_git)
    with pytest.raises(ValueError, match="clean Git checkout"):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
        )


def test_failed_database_command_still_runs_cleanup_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, corpus, evidence = _project(tmp_path)
    cleanup_calls: list[str] = []

    def fail_command(
        _command: release.QualificationCommand,
        _environment: dict[str, str],
        log_path: Path,
    ) -> int:
        log_path.write_text("failed\n")
        return 1

    def cleanup(database_url: str) -> None:
        cleanup_calls.append(database_url)

    monkeypatch.setattr(release, "_git_output", _clean_git)
    monkeypatch.setattr(release, "_run_command", fail_command)
    monkeypatch.setattr(release, "_validate_database_cleanup", cleanup)

    with pytest.raises(release.QualificationFailed):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
            run_id="release-cleanup-on-failure",
        )

    assert cleanup_calls == ["postgresql+psycopg:///leo_qualification"]


@pytest.mark.parametrize(
    "payload",
    (
        b"<not-junit/>",
        b"<testsuite tests='0' failures='0' errors='0' skipped='0'/>",
        (
            b"<testsuite tests='1' failures='1' errors='0' skipped='0'>"
            b"<testcase classname='qualification' name='failed'><failure/></testcase>"
            b"</testsuite>"
        ),
        (
            b"<testsuite tests='1' failures='0' errors='0' skipped='1'>"
            b"<testcase classname='qualification' name='skipped'><skipped/></testcase>"
            b"</testsuite>"
        ),
        (
            b"<testsuite tests='2' failures='0' errors='0' skipped='0'>"
            b"<testcase classname='qualification' name='count-mismatch'/>"
            b"</testsuite>"
        ),
        b" " * 5000 + b"<!DOCTYPE testsuite><testsuite/>",
    ),
)
def test_junit_summary_rejects_nonpassing_or_malformed_receipts(payload: bytes) -> None:
    with pytest.raises(ValueError):
        summarize_pytest_junit_v1(
            payload,
            command_name="protected-real-corpus",
            junit_relative_path="results/real-corpus.junit.xml",
        )


def test_release_evidence_inventory_rejects_symlinks(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("not evidence\n")
    (evidence / "linked.txt").symlink_to(target)

    with pytest.raises(ValueError, match="contains a symlink"):
        release._evidence_inventory(evidence)


def test_release_contract_keeps_historical_v1_readable() -> None:
    assert release_qualification_schema_version({"schema": RELEASE_QUALIFICATION_V1_SCHEMA}) == 1


def test_v3_default_inventory_excludes_expired_recording_formats() -> None:
    current = release_qualification_v3_command_documents()
    flattened = json.dumps(current, sort_keys=True)

    assert tuple(command["name"] for command in current) == RELEASE_QUALIFICATION_V3_COMMAND_NAMES
    assert "test_standard_v2_four_path_operational_vertical" not in flattened
    assert "test_real_postgres_standard_native_operational_vertical" not in flattened
    assert "test_real_postgres_mixed_capture_standard_png_and_browser_vertical" not in flattened
    assert "test_real_postgres_production_single_rx_all_rate_vertical" not in flattened
    assert "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical" in flattened

    historical = release_qualification_v3_command_documents(include_historical=True)
    historical_lane = historical[-1]
    assert historical_lane["name"] == "historical-recording-postgresql"
    assert historical_lane["release_blocking"] is False
    historical_text = json.dumps(historical_lane)
    assert "test_standard_v2_four_path_operational_vertical" not in historical_text
    assert "test_real_postgres_mixed_capture_standard_png_and_browser_vertical" not in (
        historical_text
    )


def test_v3_lane_reuse_identity_is_deterministic_and_revision_independent() -> None:
    command = release_qualification_v3_command_documents()[0]
    inputs = {
        "python-source": "1" * 64,
        "selected-tests": "2" * 64,
    }
    first = release_qualification_v3_lane_metadata(command, input_digests=inputs)
    second = release_qualification_v3_lane_metadata(
        dict(reversed(tuple(command.items()))),
        input_digests=dict(reversed(tuple(inputs.items()))),
    )

    assert first == second
    assert set(first) == {"command_sha256", "input_digests", "reuse_key_sha256"}
    assert len(first["reuse_key_sha256"]) == 64


def test_v3_lane_closures_ignore_unrelated_tests_and_isolate_api_changes(
    tmp_path: Path,
) -> None:
    project, _corpus, _evidence = _project(tmp_path)
    commands = release_qualification_v3_command_documents()
    baseline = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )

    unrelated_test = project / "tests/api/test_unrelated.py"
    unrelated_test.parent.mkdir(parents=True)
    unrelated_test.write_text("def test_unrelated(): pass\n")
    after_unrelated_test = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )
    assert after_unrelated_test == baseline

    (project / "src/leo/api/unrelated.py").write_text("API_ONLY = True\n")
    after_api = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )
    assert after_api["current-native-science"] == baseline["current-native-science"]
    assert after_api["protected-real-corpus"] == baseline["protected-real-corpus"]
    assert after_api["current-native-postgresql"] != baseline["current-native-postgresql"]
    assert after_api["production-chromium-e2e"] != baseline["production-chromium-e2e"]


def test_v3_shared_contract_and_qualification_changes_invalidate_expected_lanes(
    tmp_path: Path,
) -> None:
    project, _corpus, _evidence = _project(tmp_path)
    commands = release_qualification_v3_command_documents()
    baseline = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )

    (project / "src/leo/contracts/shared.py").write_text("CONTRACT_CHANGE = True\n")
    after_contract = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )
    for name in (
        "protected-real-corpus",
        "current-native-science",
        "current-native-postgresql",
        "production-chromium-e2e",
    ):
        assert after_contract[name] != baseline[name]
    assert after_contract["production-web-build"] == baseline["production-web-build"]

    authority = project / "src/leo/qualification/release_contract.py"
    authority.write_text(authority.read_text() + "AUTHORITY_CHANGE = True\n")
    after_authority = release._lane_input_digests(
        project,
        commands,
        python_version="3.13.0",
        platform_identity="test-platform",
    )
    assert all(after_authority[name] != after_contract[name] for name in baseline)


def test_v3_reusable_lane_requires_exact_passing_metadata() -> None:
    command = release_qualification_v3_command_documents()[0]
    metadata = release_qualification_v3_lane_metadata(
        command,
        input_digests={"python-source": "1" * 64},
    )
    expected = {**command, "lane_metadata": metadata}
    outcome = {
        "name": command["name"],
        "exit_code": 0,
        "passed": True,
        "release_blocking": True,
        "resource_units": command["resource_units"],
        "database_access": command["database_access"],
        "depends_on": command["depends_on"],
        "command_sha256": metadata["command_sha256"],
        "reuse_key_sha256": metadata["reuse_key_sha256"],
        "started_utc": "2026-09-02T00:00:00.000000Z",
        "finished_utc": "2026-09-02T00:00:01.000000Z",
        "duration_seconds": 1.0,
        "log_relative_path": command["log_relative_path"],
        "log_sha256": "3" * 64,
        "result_relative_path": "results/protected-real-corpus.junit.summary.json",
        "result_sha256": "4" * 64,
        "validation_error": None,
    }
    validate_reusable_release_qualification_v3_lane(outcome, expected)

    tampered = {**outcome, "reuse_key_sha256": "5" * 64}
    with pytest.raises(ValueError, match="not an exact reusable"):
        validate_reusable_release_qualification_v3_lane(tampered, expected)


def test_bounded_scheduler_honors_weight_and_database_exclusivity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_units = 0
    active_databases = 0
    peak_units = 0
    peak_databases = 0
    lock = threading.Lock()

    def command(name: str, units: int, *, database: bool = False) -> release.QualificationCommand:
        return release.QualificationCommand(
            name=name,
            argv=("true",),
            cwd=tmp_path,
            log_relative_path=f"logs/{name}.log",
            resource_units=units,
            database_access=database,
            depends_on=(),
            release_blocking=True,
            command_sha256="1" * 64,
            reuse_key_sha256="2" * 64,
        )

    def execute(item: release.QualificationCommand, **_kwargs: object) -> dict[str, object]:
        nonlocal active_units, active_databases, peak_units, peak_databases
        with lock:
            active_units += item.resource_units
            active_databases += int(item.database_access)
            peak_units = max(peak_units, active_units)
            peak_databases = max(peak_databases, active_databases)
        time.sleep(0.02)
        with lock:
            active_units -= item.resource_units
            active_databases -= int(item.database_access)
        return {"name": item.name, "passed": True}

    commands = (
        command("a", 2, database=True),
        command("b", 1, database=True),
        command("c", 1),
    )
    monkeypatch.setattr(release, "_execute_command", execute)
    outcomes = release._run_commands_bounded(
        commands,
        environment={},
        run_root=tmp_path,
        results_root=tmp_path,
        web_dist=tmp_path,
        database_url="postgresql+psycopg:///leo_qualification",
        maximum_resource_units=3,
    )

    assert [item["name"] for item in outcomes] == ["a", "b", "c"]
    assert peak_units <= 3
    assert peak_databases == 1


def test_release_source_marker_supports_gitless_staged_release(tmp_path: Path) -> None:
    marker = tmp_path / ".leo-release-source.json"
    marker.write_text(
        json.dumps(
            {
                "schema": "org.leo.release-source/v1",
                "revision": "a" * 40,
                "tree": "b" * 40,
            }
        )
    )
    marker.chmod(0o444)

    identity = release._source_identity(tmp_path)

    assert identity == release.SourceIdentity(
        revision="a" * 40,
        tree="b" * 40,
        kind="sealed-release-marker",
    )


def test_release_contract_recognizes_all_published_schemas() -> None:
    assert release_qualification_schema_version({"schema": RELEASE_QUALIFICATION_V2_SCHEMA}) == 2
    assert release_qualification_schema_version({"schema": RELEASE_QUALIFICATION_V3_SCHEMA}) == 3
