"""Digest-bound atomic phase sidecars, with immutable visit checkpoints."""

import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_relative_phase import RelativePhaseManifestV1, RelativePhaseVisitV1
from leo.storage.pinned import PinnedLocalRoot


class RelativePhaseJob:
    def __init__(self, directory, session_id, binding, writable):
        self.directory, self.session_id, self.binding, self.writable = (
            directory,
            session_id,
            binding,
            writable,
        )

    def read(self, name, maximum=8 * 1024 * 1024):
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.directory.fileno())
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or not 0 < info.st_size <= maximum
            ):
                raise ValueError("Invalid relative phase artifact")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(maximum + 1)
            if len(payload) != info.st_size:
                raise ValueError("Relative phase file changed during read")
            return payload
        finally:
            os.close(descriptor)

    def publish(self, name, payload):
        if not self.writable:
            raise PermissionError("Read-only phase job")
        if not 0 < len(payload) <= 8 * 1024 * 1024:
            raise ValueError("Relative phase publication exceeds bound")
        existing = self.read(name)
        if existing is not None:
            if existing != payload:
                raise ValueError("Cannot replace an immutable phase product")
            return
        temporary = f".{uuid4().hex}.partial"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o640,
            dir_fd=self.directory.fileno(),
        )
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(fd)
            os.link(
                temporary,
                name,
                src_dir_fd=self.directory.fileno(),
                dst_dir_fd=self.directory.fileno(),
                follow_symlinks=False,
            )
            os.fsync(self.directory.fileno())
        finally:
            os.close(fd)
            os.unlink(temporary, dir_fd=self.directory.fileno())

    def _document(self, name, model):
        raw = self.read(name)
        if raw is None:
            return None
        envelope = json.loads(raw)
        if envelope["sha256"] != sha256_digest(canonical_json_bytes(envelope["document"])):
            raise ValueError("Relative phase seal mismatch")
        result = model.model_validate(envelope["document"])
        if result.session_id != self.session_id or result.binding_sha256 != self.binding:
            raise ValueError("Relative phase source mismatch")
        return result

    def _publish_document(self, name, model):
        if model.session_id != self.session_id or model.binding_sha256 != self.binding:
            raise ValueError("Relative phase source mismatch")
        document = model.model_dump(mode="json")
        self.publish(
            name,
            canonical_json_bytes(
                dict(document=document, sha256=sha256_digest(canonical_json_bytes(document)))
            ),
        )

    def visit(self, index):
        if type(index) is not int or not 0 <= index < 2500:
            raise ValueError("Invalid visit index")
        row = self._document(f"visit-{index:04d}.json", RelativePhaseVisitV1)
        if row is not None and row.visit_index != index:
            raise ValueError("Phase visit changed identity")
        return row

    def write_visit(self, row):
        self._publish_document(f"visit-{row.visit_index:04d}.json", row)

    def manifest(self):
        return self._document("manifest.json", RelativePhaseManifestV1)

    def finalize(self, manifest, images):
        if len(images) != len(manifest.artifacts):
            raise ValueError("Incomplete phase artifacts")
        for artifact in manifest.artifacts:
            data = images[artifact.name]
            if (
                len(data) != artifact.byte_count
                or sha256_digest(data) != artifact.sha256
                or not data.startswith(b"\x89PNG\r\n\x1a\n")
            ):
                raise ValueError("Phase PNG binding differs")
            self.publish(artifact.name + ".png", data)
        self._publish_document("manifest.json", manifest)

    def artifact(self, name, digest):
        manifest = self.manifest()
        if manifest is None:
            return None
        artifact = next((a for a in manifest.artifacts if a.name == name), None)
        if artifact is None or artifact.sha256 != digest:
            raise ValueError("Unpublished phase artifact identity")
        data = self.read(artifact.name + ".png")
        if data is None or len(data) != artifact.byte_count or sha256_digest(data) != digest:
            raise ValueError("Relative phase artifact corrupt or missing")
        return data


class RelativePhaseStore:
    def __init__(self, root, *, read_only=False):
        self.root = root
        self.read_only = read_only

    @contextmanager
    def job(self, session_id, binding, *, writable=False):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", session_id) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", binding
        ):
            raise ValueError("Invalid phase storage identity")
        if writable and self.read_only:
            raise PermissionError("Read-only phase store")
        handles = [PinnedLocalRoot(self.root)]
        lock = None
        try:
            for part in ("scanner-adaptive-relative-phase-v1", session_id, binding[7:]):
                if not writable:
                    os.stat(part, dir_fd=handles[-1].fileno(), follow_symlinks=False)
                handles.append(handles[-1].child(part, create=writable))
            if writable:
                lock = os.open(
                    ".lock",
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o640,
                    dir_fd=handles[-1].fileno(),
                )
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield RelativePhaseJob(handles[-1], session_id, binding, writable)
        finally:
            if lock is not None:
                os.close(lock)
            for handle in reversed(handles):
                handle.close()
