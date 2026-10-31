"""Separate ALGO05 jobs over completed ALGO04 public input and export ports."""

import fcntl
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from leo.contracts.fast_graph_position_v3 import MODEL_VERSION as INCUMBENT_VERSION
from leo.contracts.fast_graph_position_v4 import MODEL_VERSION, NAMESPACE, validate_terminal
from leo.storage.fast_graph_position import sha
from leo.storage.fast_graph_position_v3_export import FastGraphPositionStoreV3Export
from leo.storage.fast_scan import safe_id
from leo.storage.uri import confined_path

LOGGER = logging.getLogger(__name__)


class FastGraphPositionStoreV4:
    def __init__(self, root, *, incumbent=None):
        self.root = Path(root).resolve()
        self.namespace = self.root / NAMESPACE / MODEL_VERSION
        self.incumbent = incumbent if incumbent is not None else FastGraphPositionStoreV3Export(self.root)

    def path(self, identifier):
        return confined_path(
            self.root, self.namespace / "jobs" / safe_id(identifier), must_exist=False
        )

    def job(self, source_job):
        if source_job["model_version"] != INCUMBENT_VERSION:
            raise ValueError("ALGO05 requires an ALGO04 source job")
        terminal, receipt = self.incumbent.terminal(source_job)
        if terminal["state"] != "complete":
            raise ValueError("ALGO05 requires a completed qualified ALGO04 incumbent")
        identifier = hashlib.sha256(
            (MODEL_VERSION + ":" + source_job["input_sha256"]).encode()
        ).hexdigest()[:32]
        public_source = {
            key: source_job[key]
            for key in (
                "job_id",
                "model_version",
                "run_id",
                "input_path",
                "input_sha256",
                "session_id",
                "source_job",
                "incumbent_terminal_sha256",
            )
        }
        return dict(
            job_id=identifier,
            model_version=MODEL_VERSION,
            run_id=source_job["run_id"],
            input_path=source_job["input_path"],
            input_sha256=source_job["input_sha256"],
            session_id=terminal["session_id"],
            source_job=public_source,
            incumbent_terminal_sha256=receipt["sha256"],
        )

    def inputs(self, *, minimum_completed_utc_ns):
        for source in self.incumbent.completed_inputs(
            minimum_completed_utc_ns=minimum_completed_utc_ns
        ):
            try:
                yield self.job(source)
            except (OSError, ValueError, KeyError, TypeError) as error:
                LOGGER.warning(
                    "Rejected ALGO05 incumbent job %s (%s): %s",
                    source.get("job_id"),
                    type(error).__name__,
                    error,
                )

    def verify_input(self, job):
        terminal, receipt = self.incumbent.terminal(job["source_job"])
        if (
            terminal["state"] != "complete"
            or terminal["session_id"] != job["session_id"]
            or receipt["sha256"] != job["incumbent_terminal_sha256"]
        ):
            raise ValueError("ALGO05 published ALGO04 incumbent changed")

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
        current, _ = self.incumbent.terminal(job["source_job"])
        if value.get("session_id") != job["session_id"] or value["incumbent"] != current:
            raise ValueError("ALGO05 terminal embeds another published ALGO04 incumbent")
        return value, dict(path=str(path), sha256=sha(path))

