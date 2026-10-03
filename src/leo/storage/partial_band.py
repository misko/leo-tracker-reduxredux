"""Immutable, resumable low-rate products in their own pinned namespace."""

import fcntl
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from leo.contracts.digests import Sha256Digest, canonical_json_bytes, sha256_digest
from leo.contracts.partial_band import (
    PARTIAL_BAND_ARTIFACTS,
    PartialBandArtifactV1,
    PartialBandBindingV1,
    PartialBandConfigurationV1,
    PartialBandManifestV1,
    PartialBandStatusV1,
    PartialBandVisitV1,
    SessionId,
    partial_band_identity,
)
from leo.storage.pinned import PinnedLocalRoot

LIMIT = 128 * 1024 * 1024


def _read(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno())
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
            raise ValueError("invalid partial-band product file")
        return stream.read(LIMIT + 1)


def _publish(directory, name, payload):
    """Publish without replacing existing evidence; interruption is retryable."""
    if len(payload) > LIMIT:
        raise ValueError("partial-band product exceeds size limit")
    try:
        existing = _read(directory, name)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing != payload:
            raise ValueError("immutable partial-band product differs")
        return
    temporary = ".tmp-" + uuid.uuid4().hex
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
        dir_fd=directory.fileno(),
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            temporary,
            name,
            src_dir_fd=directory.fileno(),
            dst_dir_fd=directory.fileno(),
            follow_symlinks=False,
        )
        os.fsync(directory.fileno())
    finally:
        os.unlink(temporary, dir_fd=directory.fileno())


class PartialBandStore:
    namespace = "scanner-partial-band-glrt-v1"

    def __init__(
        self,
        root: Path,
        *,
        read_only: bool = True,
        configuration: PartialBandConfigurationV1 | None = None,
    ):
        self.root = Path(root)
        self.read_only = read_only
        self.configuration = configuration or PartialBandConfigurationV1()

    @contextmanager
    def _directory(self, session_id, input_digest, *, create=False):
        TypeAdapter(SessionId).validate_python(session_id)
        TypeAdapter(Sha256Digest).validate_python(input_digest)
        if create and self.read_only:
            raise PermissionError("partial-band store is read-only")
        identity = partial_band_identity(session_id, input_digest, self.configuration)
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child(self.namespace, session_id, identity[7:], create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    @contextmanager
    def writer(self, binding):
        if binding.configuration != self.configuration:
            raise ValueError("writer configuration differs")
        with self._directory(binding.session_id, binding.input_manifest_sha256, create=True) as d:
            fd = os.open(
                ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640, dir_fd=d.fileno()
            )
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size:
                    raise ValueError("invalid partial-band writer lock")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _publish(d, "binding.json", canonical_json_bytes(binding.model_dump(mode="json")))
                yield PartialBandJob(d, binding)
            finally:
                os.close(fd)

    def status(self, session_id, input_manifest_sha256):
        identity = partial_band_identity(session_id, input_manifest_sha256, self.configuration)
        try:
            with self._directory(session_id, input_manifest_sha256) as d:
                binding = PartialBandBindingV1.model_validate_json(_read(d, "binding.json"))
                if binding.digest != identity:
                    raise ValueError("partial-band binding changed")
                try:
                    manifest = PartialBandManifestV1.model_validate_json(_read(d, "manifest.json"))
                except FileNotFoundError:
                    count = sum(
                        name.startswith("visit-") and name.endswith(".json")
                        for name in os.listdir(d.fileno())
                    )
                    return PartialBandStatusV1(
                        session_id=session_id,
                        binding_sha256=identity,
                        state="partial",
                        completed_visits=count,
                    )
                if manifest.binding != binding:
                    raise ValueError("partial-band manifest changed source")
                # Completion is derived from verified artifacts, not just a marker.
                for artifact in manifest.artifacts:
                    payload = _read(d, artifact.name)
                    if (
                        len(payload) != artifact.byte_count
                        or sha256_digest(payload) != artifact.sha256
                    ):
                        raise ValueError("partial-band artifact missing or corrupt")
                return PartialBandStatusV1(
                    session_id=session_id,
                    binding_sha256=identity,
                    state="figures_ready",
                    completed_visits=len(binding.visits),
                    manifest=manifest,
                )
        except ValueError as error:
            if not isinstance(error.__cause__, FileNotFoundError):
                raise
        except FileNotFoundError:
            # A missing artifact under a sealed manifest must not become not_started.
            if "manifest" in locals():
                raise ValueError("sealed partial-band artifact is missing") from None
        return PartialBandStatusV1(
            session_id=session_id, binding_sha256=identity, state="not_started", completed_visits=0
        )

    def read_checkpoint(self, session_id, input_manifest_sha256, index):
        with self._directory(session_id, input_manifest_sha256) as directory:
            binding = PartialBandBindingV1.model_validate_json(_read(directory, "binding.json"))
            if type(index) is not int or not 0 <= index < len(binding.visits):
                raise ValueError("invalid partial-band checkpoint index")
            return PartialBandJob(directory, binding).checkpoint(index)

    def import_completed(self, source, session_id, input_manifest_sha256):
        """Copy verified published products through ports, never capture paths."""
        status = source.status(session_id, input_manifest_sha256)
        if status.state != "figures_ready" or status.manifest is None:
            raise ValueError("source partial-band publication is incomplete")
        manifest = status.manifest
        with self.writer(manifest.binding) as job:
            for index, digest in enumerate(manifest.checkpoint_sha256):
                checkpoint = source.read_checkpoint(session_id, input_manifest_sha256, index)
                if (
                    checkpoint is None
                    or sha256_digest(canonical_json_bytes(checkpoint.model_dump(mode="json")))
                    != digest
                ):
                    raise ValueError("source partial-band checkpoint changed")
                job.publish_checkpoint(checkpoint)
            artifacts = {
                a.name: source.artifact(session_id, input_manifest_sha256, a.name, a.sha256)
                for a in manifest.artifacts
            }
            copied = job.finish(artifacts)
            if copied != manifest:
                raise ValueError("partial-band import changed published authority")
        return copied

    def artifact(self, session_id, input_manifest_sha256, name, expected_sha256):
        if name not in PARTIAL_BAND_ARTIFACTS:
            raise ValueError("unknown partial-band artifact")
        status = self.status(session_id, input_manifest_sha256)
        if status.manifest is None:
            return None
        reference = next(a for a in status.manifest.artifacts if a.name == name)
        if reference.sha256 != expected_sha256:
            raise ValueError("partial-band artifact request changes digest")
        with self._directory(session_id, input_manifest_sha256) as d:
            data = _read(d, name)
        if sha256_digest(data) != reference.sha256:
            raise ValueError("partial-band artifact changed during read")
        return data


class PartialBandJob:
    def __init__(self, directory, binding):
        self.directory, self.binding = directory, binding

    def checkpoint(self, index):
        try:
            result = PartialBandVisitV1.model_validate_json(
                _read(self.directory, f"visit-{index:06d}.json")
            )
        except FileNotFoundError:
            return None
        result.validate_binding(self.binding)
        if result.visit_index != index:
            raise ValueError("checkpoint visit index changed")
        return result

    def publish_checkpoint(self, result):
        result.validate_binding(self.binding)
        _publish(
            self.directory,
            f"visit-{result.visit_index:06d}.json",
            canonical_json_bytes(result.model_dump(mode="json")),
        )

    def finish(self, artifacts):
        if set(artifacts) != set(PARTIAL_BAND_ARTIFACTS):
            raise ValueError("partial-band artifacts are incomplete")
        hashes, probes, passed = [], 0, 0
        for i in range(len(self.binding.visits)):
            result = self.checkpoint(i)
            if result is None:
                raise ValueError("cannot seal missing visits")
            raw = _read(self.directory, f"visit-{i:06d}.json")
            hashes.append(sha256_digest(raw))
            probes += len(result.probes)
            passed += sum(p.state == "candidate" for p in result.probes)
        references = []
        for name in PARTIAL_BAND_ARTIFACTS:
            raw = artifacts[name]
            if name.endswith(".png") and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("partial-band figure is not PNG")
            _publish(self.directory, name, raw)
            references.append(
                PartialBandArtifactV1(name=name, sha256=sha256_digest(raw), byte_count=len(raw))
            )
        manifest = PartialBandManifestV1(
            binding_sha256=self.binding.digest,
            binding=self.binding,
            checkpoint_sha256=tuple(hashes),
            probe_count=probes,
            candidate_probe_count=passed,
            artifacts=tuple(references),
        )
        _publish(
            self.directory, "manifest.json", canonical_json_bytes(manifest.model_dump(mode="json"))
        )
        return manifest
