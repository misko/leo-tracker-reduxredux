"""Immutable phase checkpoints and hash-bound PNGs."""

import pytest

from leo.contracts.digests import sha256_digest
from leo.presentation.adaptive_relative_phase import render_relative_phase
from leo.scanner.adaptive_relative_phase import (
    RelativePhaseArtifactV1,
    RelativePhaseManifestV1,
    RelativePhaseVisitV1,
)
from leo.storage.adaptive_relative_phase import RelativePhaseStore

DIGEST = "sha256:" + "1" * 64
SESSION = "scan-hop-0123456789abcdef"


def publish_empty(root):
    images = render_relative_phase([], session_id=SESSION, total_visits=12)
    manifest = RelativePhaseManifestV1(
        session_id=SESSION,
        input_manifest_sha256=DIGEST,
        glrt_binding_sha256=DIGEST,
        binding_sha256=DIGEST,
        state="insufficient_signal",
        total_visit_count=12,
        selected_visits=(),
        supported_visit_count=0,
        pilot_checked_visit_count=0,
        receiver_geometry_digest=None,
        artifacts=tuple(
            RelativePhaseArtifactV1(name=name, sha256=sha256_digest(data), byte_count=len(data))
            for name, data in images.items()
        ),
    )
    with RelativePhaseStore(root).job(SESSION, DIGEST, writable=True) as job:
        job.finalize(manifest, images)
    return manifest, images


def test_empty_scan_publishes_pngs_and_rejects_wrong_digest(tmp_path):
    manifest, images = publish_empty(tmp_path)
    with RelativePhaseStore(tmp_path, read_only=True).job(SESSION, DIGEST) as job:
        assert job.manifest() == manifest
        for a in manifest.artifacts:
            assert job.artifact(a.name, a.sha256) == images[a.name]
            with pytest.raises(ValueError, match="identity"):
                job.artifact(a.name, DIGEST)
        with pytest.raises(PermissionError):
            job.publish("test", b"x")


def test_checkpoint_is_immutable_and_detects_corruption(tmp_path):
    row = RelativePhaseVisitV1(
        session_id=SESSION,
        binding_sha256=DIGEST,
        visit_index=3,
        state="insufficient_signal",
        reason="test",
        evidence={},
    )
    with RelativePhaseStore(tmp_path).job(SESSION, DIGEST, writable=True) as job:
        job.write_visit(row)
        job.write_visit(row)
        assert job.visit(3) == row
        with pytest.raises(ValueError, match="immutable"):
            job.write_visit(row.model_copy(update={"reason": "changed"}))
    path = (
        tmp_path / "scanner-adaptive-relative-phase-v1" / SESSION / DIGEST[7:] / "visit-0003.json"
    )
    path.write_bytes(path.read_bytes().replace(b'"test"', b'"evil"'))
    with (
        RelativePhaseStore(tmp_path).job(SESSION, DIGEST) as job,
        pytest.raises(ValueError, match="seal"),
    ):
        job.visit(3)


def test_path_escape_and_symlink_rejected(tmp_path):
    with (
        pytest.raises(ValueError),
        RelativePhaseStore(tmp_path).job("../escape", DIGEST, writable=True),
    ):
        pass
    (tmp_path / "scanner-adaptive-relative-phase-v1").symlink_to(tmp_path, target_is_directory=True)
    with (
        pytest.raises(ValueError),
        RelativePhaseStore(tmp_path).job(SESSION, DIGEST, writable=True),
    ):
        pass
