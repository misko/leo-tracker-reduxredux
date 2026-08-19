from __future__ import annotations

import os
from pathlib import Path

import pytest

from leo.artifacts import AnalysisArtifactStore
from leo.pipeline import ProductSpec
from leo.storage import BundleNotFoundError, PinnedLocalRoot, RecordingStore
from leo.storage import pinned as pinned_module

from .test_recording_store import _prepare_bundle


def test_pinned_stores_survive_root_path_swap_without_alternate_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "pinned-recording")
    prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    pinned.close()
    reused = [os.open("/dev/null", os.O_RDONLY) for _index in range(8)]

    retained = tmp_path / "retained"
    alternate = tmp_path / "alternate"
    (alternate / "recordings" / "2026" / "01" / "01" / "missing").mkdir(parents=True)
    root.rename(retained)
    root.symlink_to(alternate, target_is_directory=True)

    try:
        published = artifacts.publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="stage-a",
            scope_key="scope-a",
            product=ProductSpec(kind="pinned.product"),
            document={"pinned": True},
        )

        assert artifacts.read_json(published.logical_uri, published.digest) == {"pinned": True}
        assert recordings.inspect("pinned-recording").manifest == prepared.manifest
        assert recordings.read_ci16("pinned-recording", "stream-a", 0, 6).shape == (6, 2, 2)
        assert tuple((retained / "analysis").rglob("pinned.product.v1.json"))
        assert not (alternate / "analysis").exists()
        with pytest.raises(BundleNotFoundError):
            recordings.inspect("missing")
    finally:
        for descriptor in reused:
            os.close(descriptor)


def test_pinned_stores_survive_namespace_swap_without_target_access(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "namespace-recording")
    prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    pinned.close()

    retained_recordings = root / "recordings-retained"
    retained_analysis = root / "analysis-retained"
    retained_spool_analysis = root / "spool" / "analysis-retained"
    alternate = tmp_path / "alternate"
    alternate_recordings = alternate / "recordings"
    alternate_analysis = alternate / "analysis"
    alternate_spool_analysis = alternate / "spool-analysis"
    for directory in (alternate_recordings, alternate_analysis, alternate_spool_analysis):
        directory.mkdir(parents=True)
    (root / "recordings").rename(retained_recordings)
    (root / "recordings").symlink_to(alternate_recordings, target_is_directory=True)
    (root / "analysis").rename(retained_analysis)
    (root / "analysis").symlink_to(alternate_analysis, target_is_directory=True)
    (root / "spool" / "analysis").rename(retained_spool_analysis)
    (root / "spool" / "analysis").symlink_to(
        alternate_spool_analysis,
        target_is_directory=True,
    )

    published = artifacts.publish_json(
        session_id="session-child",
        run_id="run-child",
        stage_key="stage-child",
        scope_key="scope-child",
        product=ProductSpec(kind="pinned.child-product"),
        document={"retained": True},
    )

    assert artifacts.read_json(published.logical_uri, published.digest) == {"retained": True}
    assert recordings.inspect("namespace-recording").manifest == prepared.manifest
    assert recordings.read_ci16("namespace-recording", "stream-a", 0, 6).shape == (6, 2, 2)
    assert tuple(retained_analysis.rglob("pinned.child-product.v1.json"))
    assert not tuple(alternate_analysis.rglob("*"))
    assert not tuple(alternate_spool_analysis.rglob("*"))
    assert not tuple(alternate_recordings.rglob("*"))


def test_pinned_root_rejects_qnap_before_any_filesystem_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[object] = []

    def forbidden_open(*args: object, **kwargs: object) -> int:
        probes.append((args, kwargs))
        raise AssertionError("QNAP target reached a filesystem syscall")

    monkeypatch.setattr(pinned_module.os, "open", forbidden_open)
    with pytest.raises(ValueError, match="absolute local storage"):
        PinnedLocalRoot(Path("/mnt/qnap01/never-probe"))
    assert probes == []


def test_pinned_root_does_not_follow_ancestor_symlink_toward_qnap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = tmp_path / "qnap-link"
    link.symlink_to("/mnt/qnap01/never-probe", target_is_directory=True)
    real_open = pinned_module.os.open
    probes: list[object] = []

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        probes.append(path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(pinned_module.os, "open", observed_open)
    with pytest.raises(ValueError, match="symlink component"):
        PinnedLocalRoot(link)

    assert "/mnt/qnap01/never-probe" not in probes
