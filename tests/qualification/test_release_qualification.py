from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest

from leo.qualification import release


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
        if command.name == "protected-real-corpus":
            junit = next(
                Path(item.removeprefix("--junitxml="))
                for item in command.argv
                if item.startswith("--junitxml=")
            )
            junit.write_text("<testsuite failures='0'/>\n")
        elif command.name == "production-web-build":
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
        "production-web-build",
        "production-chromium-e2e",
    ]
    assert definition["source"]["git_revision"] == "a" * 40
    assert definition["commands"][0]["argv"][:4] == [
        "uv",
        "run",
        "--frozen",
        "--no-sync",
    ]
    qualification_argv = definition["commands"][0]["argv"]
    assert any("one_path_one_coarse_window" in item for item in qualification_argv)
    assert any("standard_v2_operational_vertical" in item for item in qualification_argv)
    assert not any("full_four_path_twice" in item for item in qualification_argv)
    assert definition["isolation"]["database"] == "postgresql+psycopg:///leo_qualification"
    assert definition["isolation"]["qnap_access"] == "forbidden"
    build_argv = definition["commands"][1]["argv"]
    assert build_argv[:3] == ["npm", "--prefix", "$SCRATCH_ROOT/web"]
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
        assert environment["LEO_TEST_DATABASE_URL"].endswith("/leo_qualification")
        assert environment["LEO_E2E_DATABASE_URL"].endswith("/leo_qualification")
        assert environment["LEO_REAL_CORPUS_ROOT"] == str(corpus)
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
    assert "without the required" in receipt["commands"][0]["validation_error"]
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
