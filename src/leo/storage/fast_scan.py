"""Verified fast-scan source snapshots and immutable UI publications."""

import json
import os
import re
import time
import uuid
from pathlib import Path

from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.storage.uri import confined_path
from leo.storage.writer import _fsync_directory


def safe_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError("invalid fast-scan identifier")
    return value


def immutable_json(path, document):
    content = canonical_json_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.partial")
    with temporary.open("xb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    try:
        try:
            os.link(temporary, path)
            _fsync_directory(path.parent)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("immutable fast-scan publication changed") from None
    finally:
        temporary.unlink()


class FastSegmentSource:
    def __init__(self, entry):
        from leo.storage.short_window import ShortWindowReader
        self.reader = ShortWindowReader(Path(entry["path"]))
        if self.reader.manifest_sha256 != entry["manifest_digest"]:
            raise ValueError("fast-scan source manifest changed")
        self.manifest_digest = self.reader.manifest_sha256
        self.receiver_ids = self.reader.manifest.receiver_ids
        self.radio = self.reader.manifest.radio
        self.targets = {t["target_id"]: t for t in self.reader.manifest.configuration["targets"]}
        configuration = self.reader.manifest.configuration
        if (
            configuration.get("sample_rate_hz") != 2500000
            or self.reader.manifest.sample_rate_hz != 2500000
        ):
            raise ValueError("fast-scan predictor is qualified only at 2.5 MS/s")
        if not self.targets or len(self.targets) != len(configuration["targets"]):
            raise ValueError("fast-scan targets must be nonempty and unique")
        for target in self.targets.values():
            if (
                target.get("edge") not in ("lower", "upper")
                or target.get("channel") not in range(1, 9)
                or type(target.get("rf_center_hz")) is not int
                or type(target.get("lnb_lo_hz")) is not int
            ):
                raise ValueError("fast-scan GLRT requires an explicit channel and RF/LO hypothesis")
        if not 1 <= self.reader.manifest.window_count <= 4096:
            raise ValueError("fast-scan segment must contain 1 to 4096 windows")

    def windows(self):
        from leo.scanner.fast_scan_analysis import VerifiedFastWindow
        for w in self.reader.windows():
            yield VerifiedFastWindow(
                w.index.sequence,
                w.index.iq_sha256,
                w.index.acquisition,
                self.targets[w.index.target_id],
                w.samples,
            )


class FastScanStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if self.root == Path("/mnt/qnap01") or Path("/mnt/qnap01") in self.root.parents:
            raise ValueError("fast-scan output must be local")

    def _path(self, namespace, name=None):
        # Resolve each owned descendant through the storage confinement port.
        # Missing roots are permitted for read-only empty UI listings.
        if not self.root.exists():
            return self.root / namespace if name is None else self.root / namespace / name
        candidate = self.root / namespace if name is None else self.root / namespace / name
        return confined_path(self.root, candidate, must_exist=False)

    def ingest(self, recording):
        from leo.storage.short_window import ShortWindowReader
        recording = Path(recording).resolve(strict=True)
        paths = (
            [recording]
            if (recording / "manifest.json").is_file()
            else sorted(
                p.parent
                for p in recording.glob("*/manifest.json")
                if not p.parent.name.startswith(".")
            )
        )
        if not paths:
            raise ValueError("no sealed fast-scan segments")
        entries = []
        previous = None
        generation = None
        configuration_digest = None
        previous_end = None
        for path in paths:
            reader = ShortWindowReader(path)
            binding = canonical_digest(
                [reader.manifest.configuration, reader.manifest.radio, reader.manifest.receiver_ids]
            )
            if configuration_digest is not None and binding != configuration_digest:
                raise ValueError("mixed fast-scan configurations or radios")
            configuration_digest = binding
            entry = {
                "scope": f"segment-{len(entries):08d}",
                "path": str(path),
                "manifest_digest": reader.manifest_sha256,
                "windows": reader.manifest.window_count,
            }
            for w in FastSegmentSource(entry).windows():
                visit = w.acquisition["global_visit"]
                current_generation = w.acquisition.get("generation")
                if previous is not None and visit != previous + 1:
                    raise ValueError("nonconsecutive visit inventory")
                if previous is not None and current_generation != generation:
                    raise ValueError("mixed stream generations")
                start = w.acquisition.get("sample_start")
                if type(start) is int and previous_end is not None and start < previous_end:
                    raise ValueError("overlapping or regressed sample counters")
                end = w.acquisition.get("sample_end")
                if type(end) is int:
                    previous_end = end
                previous = visit
                generation = current_generation
            entries.append(entry)
        inventory = {
            "schema_version": 1,
            "kind": "fast-scan-source",
            "recording_name": recording.name,
            "segments": entries,
            "window_count": sum(e["windows"] for e in entries),
        }
        digest = canonical_digest(inventory)
        session_id = "fast-" + digest.removeprefix("sha256:")[:32]
        immutable_json(self._path("fast-scan-inputs", f"{session_id}.json"), inventory)
        return session_id, digest, inventory

    def source(self, session_id, digest):
        path = self._path("fast-scan-inputs", f"{safe_id(session_id)}.json")
        doc = json.loads(path.read_bytes())
        if canonical_digest(doc) != digest:
            raise ValueError("fast-scan inventory changed")
        return doc

    def publish(self, run_id, report):
        immutable_json(self._path("fast-scan-reports", f"{safe_id(run_id)}.json"), report)

    def publish_tracking_input(self, run_id, document):
        path = self._path("fast-scan-tracking-inputs", f"{safe_id(run_id)}.json")
        immutable_json(path, document)
        return path

    def automatic_status(self, recording_id):
        path = self._path("fast-scan-automatic", f"{safe_id(recording_id)}.json")
        return json.loads(path.read_bytes()) if path.exists() else None

    def update_automatic(self, recording_id, **changes):
        document = self.automatic_status(recording_id) or {"recording_id": recording_id}
        document.update(changes, updated_utc_ns=time.time_ns())
        path = self._path("fast-scan-automatic", f"{safe_id(recording_id)}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
        return document

    def automatic_page(self, limit=100):
        if not 1 <= limit <= 100:
            raise ValueError("invalid page limit")
        paths = sorted(self._path("fast-scan-automatic").glob("*.json"),
                       key=lambda p: p.stat().st_mtime_ns, reverse=True)[:limit]
        return {"items": [self.automatic_status(p.stem) for p in paths]}

    def automatic_workspace(self, recording_id):
        path = self._path("fast-scan-automatic-work", safe_id(recording_id))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def tracking_input_path(self, run_id):
        return self._path("fast-scan-tracking-inputs", f"{safe_id(run_id)}.json")

    def page(self, limit=20):
        if not 1 <= limit <= 100:
            raise ValueError("invalid page limit")
        root = self._path("fast-scan-reports")
        paths = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[
            :limit
        ]
        return {"items": [self.detail(p.stem, include_points=False) for p in paths]}

    def detail(self, run_id, include_points=True):
        path = self._path("fast-scan-reports", f"{safe_id(run_id)}.json")
        if not path.is_file():
            raise FileNotFoundError(run_id)
        report = json.loads(path.read_bytes())
        if not include_points:
            report.pop("points", None)
        return report


class FastScanReaderProvider:
    def __init__(self, store):
        self.store = store

    def open(self, execution, scope_key):
        inventory = self.store.source(execution.session_id, execution.input_manifest_digest)
        matches = [e for e in inventory["segments"] if e["scope"] == scope_key]
        if len(matches) != 1:
            raise ValueError("unknown fast-scan segment scope")
        return FastSegmentSource(matches[0])

    def open_scope(self, *args):
        raise ValueError("fast scans use segment scopes")

    def close(self):
        pass
