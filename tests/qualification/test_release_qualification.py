from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest

from leo.qualification import release
from leo.qualification.release_contract import (
    RELEASE_QUALIFICATION_V1_SCHEMA,
    release_qualification_schema_version,
    summarize_pytest_junit_v1,
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
    corpus = tmp_path / "protected-corpus"
    corpus.mkdir()
    evidence = tmp_path / "evidence"
    return project.resolve(), corpus.resolve(), evidence.resolve()


def _clean_git(_project: Path, *arguments: str) -> str:
    return "a" * 40 if arguments == ("rev-parse", "HEAD") else ""


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
    assert [item["name"] for item in receipt["commands"]] == [
        "protected-real-corpus",
        "standard-native-science",
        "standard-native-postgresql",
        "standard-native-real-corpus",
        "production-web-build",
        "production-chromium-e2e",
    ]
    assert receipt["schema"] == "org.leo.release-qualification/v2"
    assert definition["schema"] == "org.leo.release-qualification/v2"
    assert definition["source"]["git_revision"] == "a" * 40
    assert definition["commands"][0]["argv"][:4] == [
        "uv",
        "run",
        "--frozen",
        "--no-sync",
    ]
    qualification_argv = definition["commands"][0]["argv"]
    assert any("one_path_one_coarse_window" in item for item in qualification_argv)
    assert any("standard_v2_four_path_operational_vertical" in item for item in qualification_argv)
    assert not any("full_four_path_twice" in item for item in qualification_argv)
    assert definition["isolation"]["database"] == "postgresql+psycopg:///leo_qualification"
    assert definition["isolation"]["qnap_access"] == "forbidden"
    assert definition["isolation"]["native_rate_corpus_root"] == str(corpus)
    assert definition["commands"][1]["name"] == "standard-native-science"
    assert (
        "tests/analysis/test_standard_native_scientific_equivalence.py"
        in (definition["commands"][1]["argv"])
    )
    assert definition["commands"][2]["name"] == "standard-native-postgresql"
    assert any(
        "test_real_postgres_standard_native_operational_vertical" in item
        for item in definition["commands"][2]["argv"]
    )
    assert any(
        "test_real_postgres_promoted_gapped_native_run_is_presented_as_current_partial" in item
        for item in definition["commands"][2]["argv"]
    )
    assert any(
        "test_real_postgres_mixed_capture_standard_png_and_browser_vertical" in item
        for item in definition["commands"][2]["argv"]
    )
    assert any(
        "test_real_postgres_production_single_rx_all_rate_vertical" in item
        for item in definition["commands"][2]["argv"]
    )
    assert any(
        "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical" in item
        for item in definition["commands"][2]["argv"]
    )
    assert definition["commands"][3]["name"] == "standard-native-real-corpus"
    assert "real_corpus" in definition["commands"][3]["argv"]
    build_argv = definition["commands"][4]["argv"]
    assert build_argv[:3] == ["npm", "--prefix", "$SCRATCH_ROOT/web"]
    assert build_argv[3:5] == ["run", "qualify:release"]
    assert any(item.startswith("$SCRATCH_ROOT/") for item in build_argv)
    assert not any("leo-release-qualification-" in item for item in build_argv)
    assert any(
        item["relative_path"] == "results/real-corpus.junit.xml" for item in receipt["evidence"]
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

    with pytest.raises(FileExistsError):
        release.run_release_qualification(
            project_root=project,
            database_url="postgresql+psycopg:///leo_qualification",
            corpus_root=corpus,
            evidence_root=evidence,
            run_id="release-test-pass",
        )


def test_release_lane_stops_after_corpus_failure_and_preserves_failure_receipt(
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
    assert invoked == ["protected-real-corpus"]
    assert receipt["status"] == "failed"
    assert receipt["passed"] is False
    assert receipt["commands"][0]["exit_code"] == 1


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
        return "a" * 40 if arguments == ("rev-parse", "HEAD") else " M source.py"

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
