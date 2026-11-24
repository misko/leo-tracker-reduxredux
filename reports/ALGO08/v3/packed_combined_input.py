"""Read opt-in packed members through the combined receiver's window-source port."""

from contextlib import ExitStack, closing, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

import ci16_packing
import seekable_member as seek


SCHEMA = "private-algo08-packed-input-map-v1"
INPUT_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError)


def pin(text):
    if not isinstance(text, str):
        raise ValueError("Expected a SHA-256 pin")
    value = text.removeprefix("sha256:")
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("Expected a lowercase SHA-256 pin")
    return "sha256:" + value


def member_map(content):
    doc = json.loads(content)
    if doc["schema"] != SCHEMA:
        raise ValueError("Unknown packed input map schema")
    entries = {}
    for item in doc["members"]:
        name, chunk = item["directory"], item["chunk_index"]
        if (not isinstance(name, str) or Path(name).parts != (name,)
                or name in (".", "..") or type(chunk) is not int or chunk < 0):
            raise ValueError("Packed member needs a sibling directory and nonnegative chunk index")
        key = pin(item["manifest_sha256"]), chunk
        if key in entries:
            raise ValueError("Packed input map contains a repeated member")
        entries[key] = name, pin(item["seek_sha256"])
    if not entries:
        raise ValueError("Packed input map is empty")
    return pin(doc["codec_sha256"]), entries


def now():
    return process_time_ns(), perf_counter_ns()


def spent(start):
    return dict(cpu_ns=process_time_ns() - start[0], wall_ns=perf_counter_ns() - start[1])


def request(args):
    keys = ("packed_ci16_map", "packed_ci16_map_sha256", "packed_ci16_codec")
    path, digest, codec = (getattr(args, key, None) for key in keys)
    if path is None and digest is None and codec is None:
        return None
    if path is None or digest is None or codec is None:
        raise ValueError("Provide the packed input map, trusted SHA-256 and native codec together")
    return path, pin(digest), codec


def load_input(config, temporary, audit):
    path, digest, binary = config
    root = path.parent.resolve(strict=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        content = seek.read_metadata(directory, path.name)
    finally:
        os.close(directory)
    seek.check(content, digest)
    binary_pin, mapping = member_map(content)
    binary_root = os.open(binary.parent.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        native = seek.read_metadata(binary_root, binary.name)
    finally:
        os.close(binary_root)
    seek.check(native, binary_pin)
    verified = temporary / "packed-ci16-codec.so"
    seek.write(verified, native)
    codec = ci16_packing.Packing(verified)
    audit.update(map_sha256=digest, codec=codec.programme(), mapped_members=len(mapping))
    return root, mapping, codec


def admit(reader, source, chunk):
    if reader.manifest_sha256 != source.manifest_digest or reader.chunk != chunk:
        raise ValueError("Packed member belongs to a different original manifest or index")
    if any(row.target_id not in source.targets for row in reader.rows):
        raise ValueError("Packed member contains a foreign target")
    reader.verify_encoded()


def packed_windows(reader, source, record):
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow

    whole = sha256()
    decode = dict(cpu_ns=0, wall_ns=0)
    for row in reader.rows:
        start = now()
        raw = reader.read(row.sequence, full=True)
        whole.update(raw)
        samples = np.frombuffer(raw, dtype="<i2").reshape(seek.SAMPLES, 2, 2)
        for key, value in spent(start).items():
            decode[key] += value
        yield VerifiedFastWindow(row.sequence, row.iq_sha256, row.acquisition, source.targets[row.target_id],
                                 samples, sample_rate_hz=reader.manifest.sample_rate_hz)
    aggregate = "sha256:" + whole.hexdigest()
    if aggregate != reader.chunk.uncompressed_sha256:
        raise ValueError("Original decoded member digest changed")
    record.update(state="packed", checks=reader.counts(), original_decoded_sha256=aggregate,
                  encoded_blocks=reader.verified_encoded_frames, decode=decode)


@contextmanager
def packed_source(scan, config, temporary, audit):
    started = now()
    audit.update(members=[], original_windows=0)
    try:
        root, mapping, codec = load_input(config, temporary, audit)
    except INPUT_ERRORS as error:
        audit.update(fallback=str(error), setup=spent(started))
        yield
        return
    audit.update(fallback=None, setup=spent(started))

    original = scan.FastSegmentSource

    class PackedSource(original):
        def __init__(self, entry, **scope):
            super().__init__(entry, **scope)
            self.entry = entry

        def original_range(self, start, stop):
            audit["original_windows"] += stop - start
            if (start, stop) == (self.start_sequence, self.stop_sequence):
                yield from super().windows()
            else:
                yield from original(self.entry, start_sequence=start, stop_sequence=stop).windows()

        def windows(self):
            ordinary_start = self.start_sequence
            for chunk in self.reader.manifest.chunks:
                first = chunk.first_sequence
                end = first + chunk.window_count
                if first < self.start_sequence or end > self.stop_sequence:
                    continue
                choice = mapping.get((self.manifest_digest, chunk.chunk_index))
                if choice is None:
                    continue
                name, seek_pin = choice
                start = now()
                record = dict(manifest_sha256=self.manifest_digest, chunk_index=chunk.chunk_index, seek_sha256=seek_pin)
                audit["members"].append(record)
                with ExitStack() as scope:
                    try:
                        reader = scope.enter_context(seek.open_member(root / name, seek_pin, codec=codec))
                        admit(reader, self, chunk)
                    except INPUT_ERRORS as error:
                        record.update(state="fallback", reason=str(error), authenticate=spent(start))
                        continue
                    record["authenticate"] = spent(start)
                    if ordinary_start < first:
                        yield from self.original_range(ordinary_start, first)
                    # A decode or original digest failure after handoff aborts before publication.
                    with closing(packed_windows(reader, self, record)) as windows:
                        yield from windows
                    ordinary_start = end
            if ordinary_start < self.stop_sequence:
                yield from self.original_range(ordinary_start, self.stop_sequence)

    with patch.object(scan, "FastSegmentSource", PackedSource):
        yield
