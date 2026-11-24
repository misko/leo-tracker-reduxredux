"""Use a trusted optional visit index with the original signed 20/8 ms scanner."""

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from unittest.mock import patch


SCHEMA = "private-algo08-visit-frame-custody-v1"
CHUNK_FIELDS = ("chunk_index", "first_sequence", "window_count", "compressed_bytes", "compressed_sha256",
                "index_sha256", "uncompressed_sha256")
MAX_AUTHORITY_BYTES = 256_000
ROOT = Path(__file__).resolve().parents[3]


def pin(value):
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("Expected an independently supplied SHA-256 pin")
    return value


def custody(path, digest, recording):
    if not path.is_file() or path.resolve(strict=True) != path:
        raise ValueError("Use a direct immutable recording authority file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_AUTHORITY_BYTES+1)
    if len(raw) > MAX_AUTHORITY_BYTES or "sha256:"+sha256(raw).hexdigest() != pin(digest):
        raise ValueError("Visit-frame custody differs from its independently trusted digest")
    plan = json.loads(raw)
    if plan["schema"] != SCHEMA or plan["recording"] != str(recording) or recording.parent != path.parent:
        raise ValueError("Visit-frame custody belongs to a different recording")
    expected = pin(plan["inventory_sha256"])
    if plan["session_id"] != "fast-"+expected[7:39] or not plan["segments"]:
        raise ValueError("Visit-frame custody has an inconsistent session identity")
    pin(plan["raw_authority"])
    directories, total = [], 0
    for segment in plan["segments"]:
        directory = segment["directory"]
        bound = recording/directory
        if (Path(directory).parts != (directory,) or directory in (".", "..") or bound.resolve(strict=True) != bound
                or not bound.is_dir() or bound.stat().st_dev != recording.stat().st_dev):
            raise ValueError("Visit-frame segment must be inside its recording on the same filesystem")
        pin(segment["manifest_sha256"])
        first = 0
        for i, member in enumerate(segment["members"]):
            for name in ("index_sha256", "uncompressed_sha256", "compressed_sha256", "side_sha256"):
                pin(member[name])
            if (member["chunk_index"] != i or member["first_sequence"] != first or member["window_count"] <= 0
                    or member["compressed_bytes"] <= 0 or member["side_name"] != f"visit-frames-{i:06d}.json"):
                raise ValueError("Visit-frame custody does not describe consecutive members")
            first += member["window_count"]
        if first != segment["window_count"] or not first:
            raise ValueError("Visit-frame member coverage differs from its segment")
        total += first
        directories.append(directory)
    if (directories != sorted(set(directories)) or not total or total != plan["window_count"]):
        raise ValueError("Visit-frame custody has incomplete or nonconsecutive segment order")
    return plan


def bind_inventory(plan, session, digest, inventory):
    rows = [(str(Path(plan["recording"])/s["directory"]), s["manifest_sha256"], s["window_count"]) for s in plan["segments"]]
    observed = [(s["path"], s["manifest_digest"], s["windows"]) for s in inventory["segments"]]
    if (plan["session_id"], plan["inventory_sha256"], plan["window_count"], rows) != (
            session, digest, inventory["window_count"], observed):
        raise ValueError("Visit-frame custody differs from the actual ordinary inventory")


def source_class(ordinary, plan, audited, selective):
    import numpy as np

    class Samples:
        dtype = np.dtype("<i2")
        flags = SimpleNamespace(c_contiguous=True)

        def __init__(self, member, row):
            self.shape = (row.sample_count, 2, 2)
            self.member, self.row = member, row
            self.array = None
            self.full = None

        def realize(self, full):
            if self.array is None:
                self.array = self.member.read(self.row, full=full)
                self.full = full
            elif self.full != full:
                raise ValueError("A committed visit cannot change its declared native aperture")
            return self.array

    segments = {str(Path(plan["recording"])/s["directory"]): s for s in plan["segments"]}

    class Source(ordinary):
        def __init__(self, entry, **options):
            super().__init__(entry, **options)
            self.commitment = segments[entry["path"]]
            if (self.reader.manifest_sha256 != self.commitment["manifest_sha256"] or self.start_sequence != 0
                    or self.stop_sequence != self.commitment["window_count"]):
                raise ValueError("The frame-backed reader requires its complete committed segment")

        def windows(self):
            for chunk, sealed in zip(self.reader.manifest.chunks, self.commitment["members"], strict=True):
                if any(getattr(chunk, field) != sealed[field] for field in CHUNK_FIELDS):
                    raise ValueError("Visit-frame custody differs from the actual ordinary member seal")
                side = self.reader.path/sealed["side_name"]
                if side.resolve(strict=True) != side or side.stat().st_dev != self.reader.path.stat().st_dev:
                    raise ValueError("Visit-frame index must be inside its committed segment")
                member = selective(self.reader, sealed["side_sha256"], chunk=chunk, side_name=side.name)
                for row in member.rows:
                    yield SimpleNamespace(sequence=row.sequence, iq_sha256=row.iq_sha256, acquisition=row.acquisition,
                                          target=self.targets[row.target_id], samples=Samples(member, row),
                                          sample_rate_hz=self.reader.manifest.sample_rate_hz)
                audited.append(dict(manifest_sha256=self.reader.manifest_sha256, chunk_index=chunk.chunk_index,
                                    payload_sha256=chunk.compressed_sha256, side_sha256=sealed["side_sha256"],
                                    authentication=member.authentication, metadata=member.metadata,
                                    counts=dict(member.counts)))

    return Source, Samples


@contextmanager
def binding(boot, plan, audit):
    ordinary = boot.staged_scanner
    audited = audit["members"] = []

    def prepare(sources, detector=None):
        scan = ordinary(sources, detector=detector)
        if detector is None:
            return scan
        with patch.object(sys, "path", [*sys.path, str(ROOT)]):
            from reports.ALGO08.v3 import visit_frame_reader
        from mixed_aperture_receiver import NativePath

        audit["reader_sha256"] = "sha256:"+sha256(Path(visit_frame_reader.__file__).read_bytes()).hexdigest()
        scan.FastSegmentSource, samples = source_class(scan.FastSegmentSource, plan, audited, visit_frame_reader.SelectiveMember)
        acquire, run = scan.acquire, NativePath.run

        def materialize(engine, words, lane, centre):
            if not isinstance(words, samples) or engine.maximum not in (1, 2):
                raise ValueError("Expected the committed 20/8 ms aperture")
            return run(engine, words.realize(engine.maximum == 2), lane, centre)

        def checked(session, digest, inventory, assets):
            bind_inventory(plan, session, digest, inventory)
            with patch.object(NativePath, "run", materialize):
                result = acquire(session, digest, inventory, assets)
            if result["source"]["raw_recording_authority_digest"] != plan["raw_authority"] or len(audited) != sum(
                    len(segment["members"]) for segment in plan["segments"]):
                raise ValueError("The selective traversal changed the new signed recording authority")
            processed = result["provenance"]["processed_windows"]
            touched = sum(m["counts"].get("prefix_checks", 0)+m["counts"].get("full_checks", 0) for m in audited)
            if processed != touched:
                raise ValueError("Every admitted visit must consume one checked detector aperture")
            return result

        scan.acquire = checked
        return scan

    with patch.object(boot, "staged_scanner", prepare):
        yield
