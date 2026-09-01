from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("leo_ops_release_retention", ROOT / "tools/ops.py")
assert SPEC is not None and SPEC.loader is not None
OPS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OPS
SPEC.loader.exec_module(OPS)


def _revision(index: int) -> str:
    return f"{index:040x}"


def _release_fixture(
    tmp_path: Path,
    *,
    count: int,
    current_index: int,
    previous_index: int,
) -> tuple[Path, Path, Path, tuple[str, ...]]:
    release_root = tmp_path / "opt" / "leo-tracker"
    releases = release_root / "releases"
    metadata = release_root / "release-metadata"
    releases.mkdir(parents=True)
    metadata.mkdir()
    release_root.chmod(0o755)
    releases.chmod(0o755)
    metadata.chmod(0o755)
    revisions = tuple(_revision(index) for index in range(count))
    for index, revision in enumerate(revisions):
        release = releases / revision
        release.mkdir(mode=0o750)
        (release / "payload.bin").write_bytes(bytes([index % 256]) * (index + 1) * 64)
        marker = metadata / f"{revision}.txt"
        marker.write_text(f"revision={revision}\nfixture={index}\n", encoding="utf-8")
        marker.chmod(0o440)
        timestamp = 1_800_000_000_000_000_000 + index
        os.utime(marker, ns=(timestamp, timestamp))
    current = revisions[current_index]
    for component in ("current", "current-api", "current-worker", "current-acquisition"):
        (release_root / component).symlink_to(Path("releases") / current)

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence_root.chmod(0o755)
    receipt = {
        "schema_version": 1,
        "kind": "leo-deployment-receipt",
        "healthy": True,
        "target_revision": current,
        "previous_revision": revisions[previous_index],
    }
    (evidence_root / f"deploy-20260901T000000Z-{current}.json").write_text(
        json.dumps(receipt),
        encoding="utf-8",
    )
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    return release_root, evidence_root, proc_root, revisions


def _plan(
    *,
    release_root: Path,
    evidence_root: Path,
    proc_root: Path,
    keep: int,
    explicitly_protected: tuple[str, ...] = (),
) -> dict[str, object]:
    return OPS._release_retention_plan(
        keep=keep,
        explicitly_protected=explicitly_protected,
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )


def test_plan_protects_selectors_runtime_previous_window_and_operator(
    tmp_path: Path,
) -> None:
    release_root, evidence_root, proc_root, revisions = _release_fixture(
        tmp_path,
        count=12,
        current_index=11,
        previous_index=2,
    )
    process = proc_root / "123"
    process.mkdir()
    (process / "cwd").symlink_to(release_root / "releases" / revisions[1])
    (process / "cmdline").write_bytes(b"")
    (process / "maps").write_bytes(b"")

    plan = _plan(
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        keep=3,
        explicitly_protected=(revisions[0],),
    )

    by_revision = {item["revision"]: item for item in plan["inventory"]}
    assert plan["history_complete"] is True
    assert plan["candidate_count"] == 6
    assert by_revision[revisions[0]]["protected_reasons"] == ["operator"]
    assert by_revision[revisions[1]]["protected_reasons"] == ["runtime"]
    assert by_revision[revisions[2]]["protected_reasons"] == ["previous-deployment"]
    assert "retention-window" in by_revision[revisions[9]]["protected_reasons"]
    assert set(by_revision[revisions[11]]["protected_reasons"]) == {
        "retention-window",
        "selector:acquisition",
        "selector:api",
        "selector:global",
        "selector:worker",
    }
    assert all(by_revision[revision]["action"] == "retire" for revision in revisions[3:9])


def test_apply_archives_metadata_removes_only_candidates_and_writes_receipts(
    tmp_path: Path,
) -> None:
    release_root, evidence_root, proc_root, revisions = _release_fixture(
        tmp_path,
        count=5,
        current_index=4,
        previous_index=3,
    )
    plan = _plan(
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        keep=2,
    )

    completion = OPS._apply_release_retention(
        expected_plan=plan["plan_sha256"],
        keep=2,
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        operator="pytest",
    )

    assert completion["retired_count"] == 3
    assert {item["revision"] for item in completion["retired"]} == set(revisions[:3])
    assert {path.name for path in (release_root / "releases").iterdir()} == set(revisions[3:])
    assert {path.name for path in (release_root / "release-metadata").iterdir()} == {
        f"{revision}.txt" for revision in revisions[3:]
    }
    archives = release_root / "retired-release-metadata"
    assert {path.name for path in archives.iterdir()} == {
        f"{revision}.txt" for revision in revisions[:3]
    }
    assert (evidence_root / f"release-retention-plan-{plan['plan_sha256']}.json").is_file()
    assert (evidence_root / f"release-retention-complete-{plan['plan_sha256']}.json").is_file()


def test_apply_rejects_stale_plan_before_removing_any_release(tmp_path: Path) -> None:
    release_root, evidence_root, proc_root, revisions = _release_fixture(
        tmp_path,
        count=5,
        current_index=4,
        previous_index=3,
    )
    plan = _plan(
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        keep=2,
    )
    selector = release_root / "current-api"
    selector.unlink()
    selector.symlink_to(Path("releases") / revisions[3])

    with pytest.raises(OPS.OpsError, match="plan changed"):
        OPS._apply_release_retention(
            expected_plan=plan["plan_sha256"],
            keep=2,
            release_root=release_root,
            evidence_root=evidence_root,
            proc_root=proc_root,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    assert len(tuple((release_root / "releases").iterdir())) == 5
    assert not (release_root / "retired-release-metadata").exists()


def test_interrupted_retirement_resumes_from_archived_metadata(tmp_path: Path) -> None:
    release_root, evidence_root, proc_root, revisions = _release_fixture(
        tmp_path,
        count=4,
        current_index=3,
        previous_index=2,
    )
    revision = revisions[0]
    metadata = release_root / "release-metadata" / f"{revision}.txt"
    digest = OPS.hashlib.sha256(metadata.read_bytes()).hexdigest()
    OPS._archive_release_metadata(
        revision=revision,
        metadata=metadata,
        expected_digest=digest,
        release_root=release_root,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    shutil.rmtree(release_root / "releases" / revision)

    plan = _plan(
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        keep=2,
    )
    by_revision = {item["revision"]: item for item in plan["inventory"]}
    assert by_revision[revision]["state"] == "retirement-metadata-pending"
    assert by_revision[revision]["action"] == "retire"

    OPS._apply_release_retention(
        expected_plan=plan["plan_sha256"],
        keep=2,
        release_root=release_root,
        evidence_root=evidence_root,
        proc_root=proc_root,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert not metadata.exists()
    assert (release_root / "retired-release-metadata" / f"{revision}.txt").is_file()


def test_inventory_refuses_symlink_release_and_unarchived_orphan_metadata(
    tmp_path: Path,
) -> None:
    release_root, evidence_root, proc_root, revisions = _release_fixture(
        tmp_path,
        count=4,
        current_index=3,
        previous_index=2,
    )
    candidate = release_root / "releases" / revisions[0]
    shutil.rmtree(candidate)
    candidate.symlink_to(release_root / "releases" / revisions[1])

    with pytest.raises(OPS.OpsError, match="must not be a symlink"):
        _plan(
            release_root=release_root,
            evidence_root=evidence_root,
            proc_root=proc_root,
            keep=2,
        )

    candidate.unlink()
    with pytest.raises(OPS.OpsError, match="no release or retirement archive"):
        _plan(
            release_root=release_root,
            evidence_root=evidence_root,
            proc_root=proc_root,
            keep=2,
        )


def test_retention_floor_and_qnap_paths_fail_closed() -> None:
    with pytest.raises(OPS.OpsError, match="keep at least"):
        OPS._release_retention_plan(keep=1)
    with pytest.raises(OPS.OpsError, match="QNAP"):
        OPS._assert_not_qnap(Path("/mnt/qnap01/releases"))


def test_cli_requires_root_and_exact_apply_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 1000)
    with pytest.raises(OPS.OpsError, match="requires root"):
        OPS._releases(OPS.parser().parse_args(["releases", "--plan"]))

    monkeypatch.setattr(OPS.os, "geteuid", lambda: 0)
    with pytest.raises(OPS.OpsError, match="requires --expect-plan"):
        OPS._releases(OPS.parser().parse_args(["releases", "--apply"]))


def test_release_pressure_warning_is_advisory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    releases = tmp_path / "releases"
    releases.mkdir()
    for index in range(OPS.DEFAULT_RELEASE_RETENTION + 1):
        (releases / _revision(index)).mkdir()

    OPS._warn_release_pressure(release_root=tmp_path)

    assert "RELEASE-RETENTION" in capsys.readouterr().err
