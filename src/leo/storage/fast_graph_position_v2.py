"""Separate ALGO03 jobs consume the completed ALGO02 analysis export port."""

import fcntl
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from leo.contracts.fast_graph_position_v2 import MODEL_VERSION, NAMESPACE, validate_terminal
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
