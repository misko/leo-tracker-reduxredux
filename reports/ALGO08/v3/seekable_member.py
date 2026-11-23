"""Private seekable view of one authenticated stereo 10 MS/s member."""

import json
import os
import stat
from contextlib import contextmanager
from hashlib import sha256
from time import process_time_ns

import zstandard as zstd

from leo.contracts.multirate_window_recording import ShortWindowIndexV2, ShortWindowManifestV2

SCHEMA = "private-algo08-stereo-12ms-prefix-8ms-tail-v1"
SAMPLES = 200_000
PREFIX_SAMPLES = 120_000
SAMPLE_BYTES = 8
WINDOW_BYTES = SAMPLES * SAMPLE_BYTES
PART_BYTES = (PREFIX_SAMPLES * SAMPLE_BYTES, (SAMPLES - PREFIX_SAMPLES) * SAMPLE_BYTES)
PART_FILES = ("prefix.zst", "tail.zst")
MAX_METADATA = 1 << 20
MAX_FRAME = WINDOW_BYTES + 65536


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


def check(data, pin):
    if digest(data) != pin:
        raise ValueError("Seekable member digest mismatch")


def metadata(manifest_bytes, index_bytes, chunk_index):
    manifest = ShortWindowManifestV2.model_validate_json(manifest_bytes)
    if manifest.sample_rate_hz != 10_000_000 or manifest.receiver_ids != (0, 1):
        raise ValueError("Expected an authenticated stereo 10 MS/s source")
    if type(chunk_index) is not int or not 0 <= chunk_index < len(manifest.chunks):
        raise ValueError("Seekable member index lies outside the source manifest")
    chunk = manifest.chunks[chunk_index]
    check(index_bytes, chunk.index_sha256)
    rows = [ShortWindowIndexV2.model_validate_json(line) for line in index_bytes.splitlines()]
    if len(rows) != chunk.window_count or chunk.uncompressed_bytes != len(rows) * WINDOW_BYTES:
        raise ValueError("Seekable source scope does not contain complete windows")
    for i, row in enumerate(rows):
        if (row.sequence, row.payload_offset_bytes, row.sample_count, row.receiver_count) != (
            chunk.first_sequence + i, i * WINDOW_BYTES, SAMPLES, 2,
        ):
            raise ValueError("Seekable source metadata is reordered or has bad geometry")
    return manifest, chunk, rows


def write(path, content):
    with path.open("xb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    path.chmod(0o400)


def create(reader, chunk_index, output, *, costs=None):
    """Convert only a whole member after its ordinary decoded validation finishes."""
    manifest_bytes = (reader.path / "manifest.json").read_bytes()
    check(manifest_bytes, reader.manifest_sha256)
    original = reader.manifest.chunks[chunk_index]
    index_bytes = reader._member(original.index_relative_path, original.index_bytes, original.index_sha256)
    _, chunk, rows = metadata(manifest_bytes, index_bytes, chunk_index)
    output.mkdir(mode=0o700)
    write(output / "source-manifest.json", manifest_bytes)
    write(output / "source-index.jsonl", index_bytes)
    compressor = zstd.ZstdCompressor(level=1, write_checksum=True)
    records = []
    with (output / PART_FILES[0]).open("xb") as prefix, (output / PART_FILES[1]).open("xb") as tail:
        original_windows = reader.windows(start_sequence=chunk.first_sequence,
                                          stop_sequence=chunk.first_sequence + chunk.window_count)
        for window, row in zip(original_windows, rows, strict=True):
            if window.index != row:
                raise ValueError("Original window metadata differs from the sealed index")
            raw = memoryview(window.samples).cast("B").toreadonly()
            record = {"sequence": row.sequence, "parts": []}
            for file, data in zip((prefix, tail), (raw[:PART_BYTES[0]], raw[PART_BYTES[0]:]), strict=True):
                started = process_time_ns()
                encoded = compressor.compress(data)
                record["parts"].append([file.tell(), len(encoded), digest(encoded), digest(data)])
                if costs is not None:
                    costs["split_encode_and_hash_cpu_ns"] += process_time_ns() - started
                file.write(encoded)
            records.append(record)
        for file in (prefix, tail):
            file.flush()
            os.fsync(file.fileno())
    for name in PART_FILES:
        (output / name).chmod(0o400)
    root = dict(schema=SCHEMA, original_manifest=reader.manifest_sha256,
                original_index=chunk.index_sha256, chunk_index=chunk_index, records=records)
    payload = json.dumps(root, sort_keys=True, separators=(",", ":")).encode()
    write(output / "seek.json", payload)
    return digest(payload)


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def open_regular(root_fd, name, *, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
        os.close(fd)
        raise ValueError(f"Invalid seekable object extent: {name}")
    return fd, file_identity(info), info.st_size


def held_pread(fd, identity, size, offset):
    raw = os.pread(fd, size, offset)
    if len(raw) != size or file_identity(os.fstat(fd)) != identity:
        raise ValueError("A seekable object changed during readback")
    return raw


def read_metadata(root, name):
    fd, identity, size = open_regular(root, name, maximum=MAX_METADATA)
    try:
        return held_pread(fd, identity, size, 0)
    finally:
        os.close(fd)


class Reader:
    def __init__(self, root, expected_pin):
        self.files = []
        self.payload_bytes = self.decoded_bytes = 0
        self.metadata_bytes = self.frames = self.full_checks = 0
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            inputs = [read_metadata(root_fd, name) for name in (
                "seek.json", "source-manifest.json", "source-index.jsonl",
            )]
            self.metadata_bytes = sum(map(len, inputs))
            seal, manifest_bytes, index_bytes = inputs
            check(seal, expected_pin)
            document = json.loads(seal)
            if document["schema"] != SCHEMA:
                raise ValueError("Unknown seekable member schema")
            check(manifest_bytes, document["original_manifest"])
            check(index_bytes, document["original_index"])
            self.manifest, self.chunk, self.rows = metadata(
                manifest_bytes, index_bytes, document["chunk_index"],
            )
            self.records = document["records"]
            if len(self.records) != len(self.rows):
                raise ValueError("Seek table omits an original visit")
            totals = [0, 0]
            for row, record in zip(self.rows, self.records, strict=True):
                if record["sequence"] != row.sequence or len(record["parts"]) != len(totals):
                    raise ValueError("Seek table reorders a visit or omits a part")
                for p, (offset, size, _, _) in enumerate(record["parts"]):
                    if type(size) is not int or not 0 < size <= MAX_FRAME or offset != totals[p]:
                        raise ValueError("Seek table extents overlap, reorder or omit bytes")
                    totals[p] += size
            for name, total in zip(PART_FILES, totals, strict=True):
                fd, identity, size = open_regular(root_fd, name, maximum=total)
                self.files.append((fd, identity))
                if size != total:
                    raise ValueError("Seekable container omits committed bytes")
        except BaseException:
            self.close()
            raise
        finally:
            os.close(root_fd)
        self.decoder = zstd.ZstdDecompressor()

    def close(self):
        while self.files:
            os.close(self.files.pop()[0])

    def counts(self):
        return dict(metadata_bytes=self.metadata_bytes, payload_bytes=self.payload_bytes,
                    decoded_bytes=self.decoded_bytes, frames=self.frames, full_checks=self.full_checks)

    def read(self, sequence, *, full):
        index = sequence - self.chunk.first_sequence
        if type(sequence) is not int or not 0 <= index < len(self.rows):
            raise ValueError("Requested visit is outside the committed member")
        parts = []
        row = self.rows[index]
        for i in range(2 if full else 1):
            offset, size, encoded_pin, raw_pin = self.records[index]["parts"][i]
            fd, identity = self.files[i]
            encoded = held_pread(fd, identity, size, offset)
            check(encoded, encoded_pin)
            expected = PART_BYTES[i]
            if zstd.frame_content_size(encoded) != expected:
                raise ValueError("Frame claims a different decoded extent")
            raw = self.decoder.decompress(encoded, max_output_size=expected, allow_extra_data=False)
            if len(raw) != expected:
                raise ValueError("Frame returned a different decoded extent")
            check(raw, raw_pin)
            self.payload_bytes += size
            self.decoded_bytes += expected
            self.frames += 1
            parts.append(raw)
        if not full:
            return parts[0]
        raw = b"".join(parts)
        check(raw, row.iq_sha256)
        self.full_checks += 1
        return raw

    def verify_all(self):
        whole = sha256()
        for row in self.rows:
            whole.update(self.read(row.sequence, full=True))
        expected = self.chunk.uncompressed_sha256
        if "sha256:" + whole.hexdigest() != expected:
            raise ValueError("Original decoded member digest changed")
        return expected


@contextmanager
def open_member(root, pin):
    reader = Reader(root, pin)
    try:
        yield reader
    finally:
        reader.close()
