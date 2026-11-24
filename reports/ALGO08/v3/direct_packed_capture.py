"""Direct producer and read-only source for private multichunk packed capture."""

from contextlib import ExitStack
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.storage.writer import _fsync_directory

from . import seekable_member as seek


SCHEMA = "private-direct-packed-ci16-v1"
PREFIX = 80_000
ROOT = "capture.json"


def close_file(path, document):
    encoded = canonical_json_bytes(document)
    seek.write(path, encoded)
    return seek.digest(encoded)


def write_capture(root, header, owned, counts, codec):
    if root.exists() or not counts or sum(counts) != len(owned) or any(not 0 < n <= 64 for n in counts):
        raise ValueError("Expected a new complete chronological capture")
    pending = root.with_name("." + root.name + ".partial")
    pending.mkdir(mode=0o700)
    schema, (prefix, _) = seek.layout(PREFIX, codec)
    first, chunks = 0, []
    for i, count in enumerate(counts):
        name = f"member-{i:06d}"
        path = pending / name
        path.mkdir(mode=0o700)
        records, original = [], []
        whole = sha256()
        parts = [path / name for name in codec.part_files]
        with ExitStack() as stack:
            streams = [stack.enter_context(part.open("xb")) for part in parts]
            for j, window in enumerate(owned[first:first+count]):
                row = window.index
                raw = memoryview(window.samples.reshape(-1)).cast("B")
                if ((row.sequence, row.payload_offset_bytes, row.payload_bytes) !=
                        (first+j, j*seek.WINDOW_BYTES, seek.WINDOW_BYTES)
                        or len(raw) != seek.WINDOW_BYTES or seek.digest(raw) != row.iq_sha256):
                    raise ValueError("Owned input differs from its logical index")
                original.append(canonical_json_bytes(row.model_dump(mode="json")) + b"\n")
                whole.update(raw)
                record = []
                for stream, words in zip(streams, (raw[:prefix], raw[prefix:]), strict=True):
                    encoded = codec.compress(words)
                    record.append([stream.tell(), len(encoded), seek.digest(encoded), seek.digest(words)])
                    stream.write(encoded)
                records.append(dict(sequence=row.sequence, parts=record))
            for stream in streams:
                stream.flush()
                os.fsync(stream.fileno())
        for part in parts:
            part.chmod(0o400)
        index = b"".join(original)
        seek.write(path / "source-index.jsonl", index)
        scope = dict(chunk_index=i, first_sequence=first, window_count=count,
                     uncompressed_bytes=count*seek.WINDOW_BYTES, uncompressed_sha256="sha256:"+whole.hexdigest(),
                     index_sha256=seek.digest(index))
        logical = dict(schema=SCHEMA, configuration=header.configuration, receiver_ids=list(header.receiver_ids),
                       radio=header.radio, sample_rate_hz=header.sample_rate_hz, scope=scope)
        metadata_pin = close_file(path / "source-manifest.json", logical)
        seek_pin = close_file(path / "seek.json", dict(schema=schema, chunk_index=i, original_manifest=metadata_pin,
                                                       original_index=scope["index_sha256"], records=records))
        _fsync_directory(path)
        chunks.append(dict(directory=name, seek_sha256=seek_pin, **scope))
        first += count
    document = dict(schema=SCHEMA, configuration=header.configuration, radio=header.radio,
                    receiver_ids=list(header.receiver_ids), sample_rate_hz=header.sample_rate_hz,
                    windows=first, codec_sha256=codec.programme()["binary_sha256"], chunks=chunks)
    digest = close_file(pending / ROOT, document)
    _fsync_directory(pending)
    pending.rename(root)
    _fsync_directory(root.parent)
    return digest, document


def parse_metadata(manifest_bytes, index_bytes, chunk_index, *, chunk, root):
    logical = json.loads(manifest_bytes)
    if logical["schema"] != SCHEMA or any(logical[key] != root[key] for key in
            ("configuration", "radio", "receiver_ids", "sample_rate_hz")):
        raise ValueError("A typed member belongs to another capture")
    scope = {key: value for key, value in chunk.items() if key not in ("directory", "seek_sha256")}
    if logical["scope"] != scope or chunk_index != chunk["chunk_index"]:
        raise ValueError("A typed member belongs to another chronological range")
    seek.check(index_bytes, scope["index_sha256"])
    rows = [ShortWindowIndexV2.model_validate_json(line) for line in index_bytes.splitlines()]
    if len(rows) != scope["window_count"] or any(
        (row.sequence, row.payload_offset_bytes, row.payload_bytes, row.sample_count, row.receiver_count)
        != (scope["first_sequence"] + i, i * seek.WINDOW_BYTES, seek.WINDOW_BYTES, seek.SAMPLES, 2)
        for i, row in enumerate(rows)
    ):
        raise ValueError("A packed member's original index has invalid chronology or geometry")
    return SimpleNamespace(**logical), SimpleNamespace(**scope), rows


class Capture:
    def __init__(self, path, pin, codec):
        self.path = path.resolve(strict=True)
        if self.path != path or not self.path.is_relative_to("/dev/shm"):
            raise ValueError("The experimental capture must be an exact local tmpfs path")
        fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            payload = seek.read_metadata(fd, ROOT)
        finally:
            os.close(fd)
        seek.check(payload, pin)
        self.document = root = json.loads(payload)
        self.codec = codec
        if (root["schema"] != SCHEMA or root["codec_sha256"] != codec.programme()["binary_sha256"]
                or root["sample_rate_hz"] != 10_000_000 or root["receiver_ids"] != [0, 1]
                or root["configuration"]["sample_rate_hz"] != 10_000_000
                or root["configuration"]["window_ms"] != 20 or not 0 < root["windows"] <= 4096):
            raise ValueError("Unsupported direct packed capture header")
        current = 0
        for i, chunk in enumerate(root["chunks"]):
            count = chunk["window_count"]
            if ((chunk["directory"], chunk["chunk_index"], chunk["first_sequence"]) !=
                    (f"member-{i:06d}", i, current) or not 0 < count <= 64
                    or chunk["uncompressed_bytes"] != count * seek.WINDOW_BYTES):
                raise ValueError("Invalid direct packed capture member geometry")
            current += count
        if current != root["windows"]:
            raise ValueError("Incomplete direct packed capture member coverage")
        self.entry = dict(scope="segment-00000000", path=str(path), manifest_digest=pin, windows=current)
        self.radio = root["radio"]
        self.receiver_ids = tuple(root["receiver_ids"])
        self.reader = SimpleNamespace(manifest=SimpleNamespace(sample_rate_hz=root["sample_rate_hz"]))
        targets = root["configuration"]["targets"]
        self.targets = {target["target_id"]: target for target in targets}
        if not self.targets or len(self.targets) != len(targets) or any(
            target.get("edge") not in ("lower", "upper") or target.get("channel") not in range(1, 9)
            or type(target.get("rf_center_hz")) is not int or type(target.get("lnb_lo_hz")) is not int
            for target in targets
        ):
            raise ValueError("A direct capture requires the original explicit RF/LO hypotheses")
        self.audit = []

    def inventory(self, recording, *, verify_windows=False):
        if Path(recording).resolve(strict=True) != self.path or verify_windows:
            raise ValueError("Direct capture inventory must use the enrolled first readback port")
        inventory = dict(schema_version=1, kind="private-packed-fast-scan-source-v1", recording_name=self.path.name,
                         window_count=self.entry["windows"], segments=[self.entry])
        digest = canonical_digest(inventory)
        return "fast-"+digest[7:39], digest, inventory

    def segment(self, entry, **scope):
        if entry != self.entry or scope or self.audit:
            raise ValueError("Only one complete first readback of the owned capture is in scope")
        return self

    def windows(self):
        from .packed_combined_input import packed_windows

        for chunk in self.document["chunks"]:
            record = dict(chunk_index=chunk["chunk_index"], seek_sha256=chunk["seek_sha256"])
            validate = partial(parse_metadata, chunk=chunk, root=self.document)
            with seek.open_member(self.path / chunk["directory"], chunk["seek_sha256"], codec=self.codec,
                                  prefix_samples=PREFIX, parse_metadata=validate) as reader:
                reader.verify_encoded()
                yield from packed_windows(reader, self, record)
            self.audit.append(record)
