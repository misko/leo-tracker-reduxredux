"""Separate versioned automatic shared-position jobs; legacy products stay immutable."""

import fcntl
import json
import math
import os
import time
import uuid
from contextlib import contextmanager

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.storage.fast_scan import FastScanStore, immutable_json, safe_id
from leo.storage.uri import confined_path
from leo.storage.writer import _fsync_directory


class SharedFastScanStore:
    def __init__(self, root, model_version):
        self._local = FastScanStore(root)
        self.root = self._local.root
        self.model_version = safe_id(model_version)
        self.namespace = f"fast-scan-shared-model-v1/{self.model_version}"
        self._input_hashes = {}

    def _path(self, job_id=None):
        suffix = "jobs" if job_id is None else f"jobs/{safe_id(job_id)}"
        path = self.root/self.namespace/suffix
        return confined_path(self.root, path, must_exist=False) if self.root.exists() else path

    def _file(self, job_id, name):
        path = self._path(job_id)/name
        return confined_path(self.root, path, must_exist=False) if self.root.exists() else path

    def inputs(self):
        """Newest exported source first, independent of legacy success/failure."""
        for path in self._local.exported_tracking_inputs():
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            cached = self._input_hashes.get(path)
            if cached is None or cached[0] != identity:
                cached = (identity, sha256_digest(path.read_bytes()))
                self._input_hashes[path] = cached
            digest = cached[1]
            job_id = canonical_digest(dict(model_version=self.model_version,
                                           input_sha256=digest)).removeprefix("sha256:")[:32]
            yield dict(job_id=job_id, run_id=path.stem, input_sha256=digest,
                       model_version=self.model_version, input_path=str(path))

    def detail(self, job_id):
        path = self._file(job_id, "status.json")
        if not path.exists():
            raise FileNotFoundError(job_id)
        document = json.loads(path.read_bytes())
        if "terminal" in document:
            terminal, receipt = self.terminal(document, verify_source=False)
            if receipt != document["terminal"]:
                raise ValueError("shared inference terminal digest changed")
            document["result"] = terminal
        return document

    def page(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid shared-model page limit")
        paths = sorted(self._path().glob("*/status.json"),
                       key=lambda p: p.stat().st_mtime_ns, reverse=True)[:limit]
        return dict(items=[self.detail(p.parent.name) for p in paths])

    def status(self, job_id):
        path = self._file(job_id, "status.json")
        return json.loads(path.read_bytes()) if path.exists() else None

    def workspace(self, job_id):
        path = self._path(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @contextmanager
    def owner(self, job_id):
        self.workspace(job_id)
        with self._file(job_id, "owner.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                try:
                    yield True
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def launch(self, job):
        self.workspace(job["job_id"])
        immutable_json(self._file(job["job_id"], "launch.json"), job)
        return self.update(job, state="running", failure=None)

    def launched(self, job_id):
        return self._file(job_id, "launch.json").exists()

    def verify_input(self, job):
        path = self._local.tracking_input_path(job["run_id"])
        if (str(path) != job["input_path"]
                or sha256_digest(path.read_bytes()) != job["input_sha256"]):
            raise ValueError("shared inference source changed")

    def update(self, job, **changes):
        document = dict(job, schema_version=1, kind="fast-scan.shared-position-status",
                        updated_utc_ns=time.time_ns(), **changes)
        self.workspace(job["job_id"])
        path = self._file(job["job_id"], "status.json")
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
        return document

    def terminal(self, job, *, verify_source=True):
        path = confined_path(self.root, self._path(job["job_id"])/"output"/"terminal.json",
                             must_exist=True)
        payload = path.read_bytes()
        document = json.loads(payload)
        if (document.get("schema_version") != 1
                or document.get("kind") != "fast-scan.shared-position"
                or document.get("model_version") != self.model_version
                or document.get("input_sha256") != job["input_sha256"]
                or document.get("state") not in {"complete", "unavailable", "failed"}):
            raise ValueError("shared inference terminal identity or state is invalid")
        if document["state"] == "complete":
            position, selection = document.get("position") or {}, document.get("selection") or {}
            lat, lon = position.get("latitude_deg"), position.get("longitude_deg")
            kkt = selection.get("stationarity")
            def finite(v):
                return type(v) in (float, int) and math.isfinite(v)
            if (not finite(lat) or not -90 <= lat <= 90 or not finite(lon)
                    or not -180 <= lon <= 180 or selection.get("accepted") is not True
                    or not finite(kkt) or not 0 <= kkt <= .001):
                raise ValueError("complete inference requires finite strict accepted position")
        if verify_source:
            self.verify_input(job)
        return document, dict(path=str(path), sha256=sha256_digest(payload))
