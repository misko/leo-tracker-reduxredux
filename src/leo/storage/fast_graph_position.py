"""Local versioned graph-position jobs over the public FastScanStore input port."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from leo.contracts.fast_graph_position import MODEL_VERSION, validate_terminal
from leo.storage.fast_scan import FastScanStore, safe_id
from leo.storage.uri import confined_path


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class FastGraphPositionStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.inputs_port = FastScanStore(self.root)
        self.namespace = self.root / "fast-scan-graph-position-v1" / MODEL_VERSION

    def path(self, identifier):
        path = self.namespace / "jobs" / safe_id(identifier)
        return confined_path(self.root, path, must_exist=False)

    def inputs(self):
        for path in self.inputs_port.exported_tracking_inputs():
            digest = sha(path)
            identifier = hashlib.sha256((MODEL_VERSION + ":" + digest).encode()).hexdigest()[:32]
            yield dict(job_id=identifier, run_id=path.stem, input_path=str(path),
                       input_sha256=digest, model_version=MODEL_VERSION)

    def status(self, identifier):
        path = self.path(identifier) / "status.json"
        return json.loads(path.read_text()) if path.exists() else None

    def update(self, job, **changes):
        folder = self.path(job["job_id"])
        folder.mkdir(parents=True, exist_ok=True)
        value = dict(job, updated_utc_ns=time.time_ns(), **changes)
        temporary = folder / ("." + uuid.uuid4().hex + ".partial")
        with temporary.open("x") as stream:
            json.dump(value, stream, allow_nan=False, indent=2)
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

    def verify_input(self, job):
        expected = self.inputs_port.tracking_input_path(job["run_id"])
        if str(expected) != job["input_path"] or sha(expected) != job["input_sha256"]:
            raise ValueError("Public GLRT input identity changed")

    def terminal(self, job):
        path = confined_path(self.root, self.path(job["job_id"]) / "output/terminal.json", must_exist=True)
        value = json.loads(path.read_text())
        validate_terminal(value, input_sha256=job["input_sha256"])
        self.verify_input(job)
        source = json.loads(Path(job["input_path"]).read_text())
        if value.get("session_id") != source["source"]["session_id"]:
            raise ValueError("Terminal belongs to another recording")
        return value, dict(path=str(path), sha256=sha(path))
