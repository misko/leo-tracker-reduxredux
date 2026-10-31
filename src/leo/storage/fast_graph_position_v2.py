"""Separate ALGO03 jobs consume the completed ALGO02 analysis export port."""

import fcntl
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from leo.contracts.fast_graph_position_v2 import MODEL_VERSION, NAMESPACE, validate_terminal
from leo.storage.errors import PathConfinementError
from leo.storage.fast_graph_position import FastGraphPositionStore, sha
from leo.storage.fast_scan import FastScanStore, safe_id
from leo.storage.uri import confined_path

LOGGER = logging.getLogger(__name__)


class FastGraphPositionStoreV2:
    def __init__(self, root, *, baseline=None, fast_inputs=None):
        self.root = Path(root).resolve()
        self.namespace = self.root / NAMESPACE / MODEL_VERSION
        self.baseline = baseline if baseline is not None else FastGraphPositionStore(self.root)
        self.fast_inputs = fast_inputs if fast_inputs is not None else FastScanStore(self.root)

    def fast_acquisition(self, source_job):
        document = json.loads(Path(source_job["input_path"]).read_text())
        source = document["source"]
        inventory = self.fast_inputs.source(source["session_id"], source["input_manifest_sha256"])
        if inventory.get("kind") != "fast-scan-source" or not inventory.get("segments"):
            raise ValueError("ALGO03 production requires verified fast acquisition provenance")
        return dict(
            kind=inventory["kind"],
            input_manifest_sha256=source["input_manifest_sha256"],
            session_id=source["session_id"],
            recording_name=inventory["recording_name"],
        )

    def path(self, identifier):
        return confined_path(
            self.root, self.namespace / "jobs" / safe_id(identifier), must_exist=False
        )

    def job(self, source_job):
        acquisition = self.fast_acquisition(source_job)
        terminal, receipt = self.baseline.terminal(source_job)
        if terminal["state"] != "complete" or acquisition["session_id"] != terminal["session_id"]:
            raise ValueError("ALGO03 requires a qualified completed baseline")
        identifier = hashlib.sha256(
            (MODEL_VERSION + ":" + source_job["input_sha256"]).encode()
        ).hexdigest()[:32]
        return dict(
            job_id=identifier,
            model_version=MODEL_VERSION,
            run_id=source_job["run_id"],
            input_path=source_job["input_path"],
            input_sha256=source_job["input_sha256"],
            session_id=terminal["session_id"],
            fast_acquisition=acquisition,
            source_job={
                key: source_job[key]
                for key in ("job_id", "model_version", "run_id", "input_path", "input_sha256")
            },
            baseline_terminal_sha256=receipt["sha256"],
        )

    def inputs(self, *, minimum_completed_utc_ns):
        if not isinstance(minimum_completed_utc_ns, int) or minimum_completed_utc_ns <= 0:
            raise ValueError("An explicit positive deployment cutoff is required")
        for source in self.baseline.inputs():
            try:
                status = self.baseline.status(source["job_id"])
                if (
                    status is not None
                    and status["state"] == "complete"
                    and status["updated_utc_ns"] >= minimum_completed_utc_ns
                ):
                    yield self.job(source)
            except (OSError, ValueError, KeyError, TypeError) as error:
                LOGGER.warning(
                    "Rejected ALGO03 baseline discovery for job %s (%s): %s",
                    source.get("job_id"),
                    type(error).__name__,
                    error,
                )

    def completed_inputs(self, *, minimum_completed_utc_ns):
        """Public downstream port using ALGO03's own completion cutoff.

        Unlike ``inputs``, this enumerates completed ALGO03 jobs, including a new
        recovery whose original ALGO02 baseline predates the downstream cutoff.
        """
        if (
            not isinstance(minimum_completed_utc_ns, int)
            or isinstance(minimum_completed_utc_ns, bool)
            or minimum_completed_utc_ns <= 0
        ):
            raise ValueError("An explicit positive ALGO03 completion cutoff is required")
        for path in sorted((self.namespace / "jobs").glob("*/status.json")):
            identifier = path.parent.name
            try:
                value = self.status(identifier)
                if (
                    value is None
                    or value["state"] != "complete"
                    or value["updated_utc_ns"] < minimum_completed_utc_ns
                ):
                    continue
                if value["job_id"] != identifier or value["model_version"] != MODEL_VERSION:
                    raise ValueError("ALGO03 status identity differs from its public job")
                terminal, _ = self.terminal(value)
                if terminal["state"] != "complete":
                    raise ValueError("Completed ALGO03 status lacks its qualified terminal")
                yield value
            except (OSError, ValueError, KeyError, TypeError, PathConfinementError) as error:
                LOGGER.warning(
                    "Rejected completed ALGO03 job %s (%s): %s",
                    identifier,
                    type(error).__name__,
                    error,
                )

    def export_recovery(self, job, destination):
        """Copy a verified private ALGO03 recovery tree for downstream replay.

        JSON bytes and their original path references remain unchanged. The
        consumer must verify this manifest before relocating references in its
        own working copies. Partial exports remain available for diagnosis.
        """
        status = self.status(job["job_id"])
        if status is None or status["state"] != "complete":
            raise ValueError("Only completed ALGO03 recoveries can be exported")
        incumbent, receipt = self.terminal(job)
        if incumbent["state"] != "complete":
            raise ValueError("Qualified ALGO03 terminal required")
        raw_output = self.namespace / "jobs" / safe_id(job["job_id"]) / "output"
        cursor = self.root
        for part in raw_output.relative_to(self.root).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("Recovery exports cannot traverse symbolic links")
        if (raw_output / "recovery").is_symlink():
            raise ValueError("Recovery exports cannot contain symbolic links")
        source = confined_path(self.namespace, raw_output / "recovery", must_exist=True)
        destination = Path(destination)
        if destination.absolute().is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if destination.is_symlink():
            raise ValueError("Recovery export destination cannot be a symbolic link")
        destination = destination.resolve()
        if destination.is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if (
            destination.is_relative_to(self.namespace.resolve())
            or source.is_relative_to(destination)
            or destination.is_relative_to(source)
        ):
            raise ValueError("Recovery export overlaps the production source namespace")
        destination.mkdir(parents=True, mode=0o700, exist_ok=False)
        destination.chmod(0o700)
        files = {}
        originals = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Recovery exports cannot contain symbolic links")
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = Path("recovery") / path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            before = sha(path)
            shutil.copyfile(path, target)
            target.chmod(0o600)
            if sha(path) != before or sha(target) != before:
                raise ValueError("ALGO03 recovery changed while exporting")
            files[str(relative)] = before
            originals[str(path.relative_to(source))] = before
        source_terminal = Path(receipt["path"])
        target = destination / "incumbent-terminal.json"
        shutil.copyfile(source_terminal, target)
        target.chmod(0o600)
        if sha(target) != receipt["sha256"]:
            raise ValueError("ALGO03 incumbent changed while exporting")
        files[target.name] = receipt["sha256"]
        current_paths = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Recovery exports cannot contain symbolic links")
            if path.is_file() and "__pycache__" not in path.parts:
                current_paths[str(path.relative_to(source))] = sha(path)
        current, again = self.terminal(job)
        if current_paths != originals or current != incumbent or again != receipt:
            raise ValueError("ALGO03 recovery or incumbent changed while exporting")
        descriptor = dict(
            schema_version=1,
            kind="fast-graph-recovery-export",
            model_version=MODEL_VERSION,
            root=str(destination),
            source_recovery_root=str(source),
            files=files,
            incumbent=incumbent,
            incumbent_receipt=receipt,
            source_job=dict(job),
            input_sha256=job["input_sha256"],
            session_id=incumbent["session_id"],
        )
        with (destination / "descriptor.json").open("x") as stream:
            json.dump(descriptor, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return descriptor

    def verify_input(self, job):
        if self.fast_acquisition(job["source_job"]) != job["fast_acquisition"]:
            raise ValueError("ALGO03 fast acquisition provenance changed")
        terminal, receipt = self.baseline.terminal(job["source_job"])
        if (
            terminal["state"] != "complete"
            or terminal["session_id"] != job["session_id"]
            or receipt["sha256"] != job["baseline_terminal_sha256"]
        ):
            raise ValueError("ALGO03 source baseline changed")

    def status(self, identifier):
        path = self.path(identifier) / "status.json"
        return json.loads(path.read_text()) if path.exists() else None

    def update(self, job, **changes):
        folder = self.path(job["job_id"])
        folder.mkdir(parents=True, exist_ok=True)
        value = dict(job, updated_utc_ns=time.time_ns(), **changes)
        temporary = folder / ("." + uuid.uuid4().hex + ".partial")
        with temporary.open("x") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(folder / "status.json")
        descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return value

    @contextmanager
    def owner(self, identifier):
        folder = self.path(identifier)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "owner.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                try:
                    yield True
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def terminal(self, job):
        self.verify_input(job)
        path = confined_path(
            self.root, self.path(job["job_id"]) / "output/terminal.json", must_exist=True
        )
        value = validate_terminal(json.loads(path.read_text()), input_sha256=job["input_sha256"])
        if value.get("session_id") != job["session_id"]:
            raise ValueError("ALGO03 terminal belongs to another recording")
        if sha_bytes(value["baseline"]) != sha_bytes(self.baseline.terminal(job["source_job"])[0]):
            raise ValueError("ALGO03 terminal embeds another baseline")
        return value, dict(path=str(path), sha256=sha(path))


def sha_bytes(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
