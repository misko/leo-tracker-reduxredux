"""A primitive sidecar for authenticated historical orbit source metadata."""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from stat import S_ISREG
import struct
from sys import getsizeof
from time import perf_counter_ns, process_time_ns

from historical_orbit_index import SourceIndex, UnsupportedExport, installed_guard


MAGIC = b"LEOTLE-I\x01"
MAX_BYTES = 24 * 1024 * 1024
MAX_HEADING = 4096
MAX_RECORDS = 100_000
HEADER = struct.Struct("<II")
BODY = struct.Struct("<32sI")
RECORD = struct.Struct("<Iq")


def digest_bytes(digest, *, labelled=True):
    if not isinstance(digest, str) or (labelled and not digest.startswith("sha256:")):
        raise ValueError("Expected an explicit SHA-256")
    encoded = digest.removeprefix("sha256:")
    raw = bytes.fromhex(encoded)
    if len(raw) != 32 or raw.hex() != encoded:
        raise ValueError("Expected a canonical SHA-256")
    return raw


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def versions():
    """Bind the actual strict parser and the installed accelerated epoch/export path."""
    from leo.sky import propagation
    import sgp4
    from sgp4 import api, exporter, vallado_cpp
    from tools.pipeline_eval.variants import algo08_causal_reuse as parser
    from tools.pipeline_eval.variants.experimental import tle_records

    active = parser.parse_element_set_records
    marker = getattr(active, "__module__", "")
    if (not installed_guard() or not api.accelerated
            or marker != tle_records.__name__ or active.__qualname__ != "batch_records.<locals>.parse"):
        raise UnsupportedExport("The installed strict record parser is outside the supported route")
    closure = dict(zip(active.__code__.co_freevars, active.__closure__, strict=True))
    paths = dict(implementation=__file__, source_index=SourceIndex.catalogue.__code__.co_filename,
                 parser=parser.__file__, strict_native=closure["native"].cell_contents.__file__,
                 strict_native_binding=tle_records.__file__, epoch=propagation.__file__,
                 api=api.__file__, native_sgp4=vallado_cpp.__file__, exporter=exporter.__file__)
    return dict(sgp4_version=sgp4.__version__,
                source_sha256={key: sha256(Path(path).read_bytes()).hexdigest() for key, path in paths.items()})


@dataclass(frozen=True)
class Artifact:
    payload: bytes
    bodies: dict

    def rows(self, digest):
        match = self.bodies.get(digest.removeprefix("sha256:"))
        if match is None:
            return None
        offset, count = match
        view = memoryview(self.payload)[offset:offset+count*RECORD.size]
        return count, RECORD.iter_unpack(view)

    def size(self):
        return (getsizeof(self.payload) + getsizeof(self.bodies)
                + sum(getsizeof(digest) + getsizeof(row) + sum(map(getsizeof, row))
                      for digest, row in self.bodies.items()))


def decode(payload, pin, compatibility):
    if len(payload) > MAX_BYTES or sha256(payload).digest() != digest_bytes(pin):
        raise ValueError("Orbit index exceeds the byte bound or differs from the external SHA-256")
    if len(payload) < len(MAGIC)+HEADER.size or not payload.startswith(MAGIC):
        raise ValueError("Invalid orbit index version")
    heading_size, bodies = HEADER.unpack_from(payload, len(MAGIC))
    start = len(MAGIC)+HEADER.size
    cursor = start+heading_size
    if (not 0 < heading_size <= MAX_HEADING or cursor > len(payload)
            or payload[start:cursor] != canonical(compatibility)):
        raise ValueError("Orbit index preparation and implementation versions differ")
    if bodies > (len(payload)-cursor)//(BODY.size+RECORD.size):
        raise ValueError("Orbit index source count exceeds the file")
    offsets, previous = {}, b""
    for _ in range(bodies):
        if len(payload)-cursor < BODY.size:
            raise ValueError("Truncated orbit index source")
        digest, count = BODY.unpack_from(payload, cursor)
        cursor += BODY.size
        if (digest <= previous or not 0 < count <= MAX_RECORDS or len(payload)-cursor < count*RECORD.size):
            raise ValueError("Invalid ordered orbit index source or row count")
        offsets[digest.hex()] = cursor, count
        cursor += count*RECORD.size
        previous = digest
    if cursor != len(payload):
        raise ValueError("Unexpected trailing bytes in the orbit index")
    return Artifact(payload, offsets)


def write_index(file, source, compatibility):
    header = canonical(compatibility)
    if not 0 < len(header) <= MAX_HEADING:
        raise ValueError("Orbit index heading exceeds the byte bound")
    payload = bytearray(MAGIC + HEADER.pack(len(header), len(source.bodies)) + header)
    bodies = sorted(((digest_bytes(digest, labelled=False), cat) for digest, cat in source.bodies.items()),
                    key=lambda entry: entry[0])
    previous = b""
    for digest, cat in bodies:
        count = len(cat.names)
        if (digest <= previous or not 0 < count <= MAX_RECORDS
                or len(payload)+BODY.size+count*RECORD.size > MAX_BYTES):
            raise ValueError("Orbit index source is duplicated or exceeds the record or byte bound")
        previous = digest
        payload.extend(BODY.pack(digest, count))
        for _, number, epoch in zip(cat.names, cat.satellite_numbers, cat.epochs, strict=True):
            if number <= 0:
                raise ValueError("Invalid native catalogue object number")
            payload.extend(RECORD.pack(number, epoch))
    pin = "sha256:"+sha256(payload).hexdigest()
    with file.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(sha256=pin, bytes=len(payload), bodies=len(source.bodies))


def load_index(file, pin, compatibility):
    start = process_time_ns(), perf_counter_ns()
    artifact, error, size = None, None, 0
    try:
        descriptor = os.open(file, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("Orbit index must be a bounded regular file")
            payload = stream.read(MAX_BYTES+1)
        size = len(payload)
        artifact = decode(payload, pin, compatibility)
    except (OSError, ValueError) as exc:
        error = str(exc)
    return artifact, dict(read_bytes=size, artifact_peak_bytes=artifact.size() if artifact else 0,
                          fallback=error, cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])


class PortableSourceIndex(SourceIndex):
    """Use a trusted primitive only after matching the original strict record sequence."""

    def __init__(self, artifact):
        super().__init__()
        self.artifact = artifact
        self.counts = dict(sidecar_hit_bodies=0, sidecar_hit_rows=0, cold_bodies=0, invalid_bodies=0,
                           strict_reparse_cpu_ns=0, attach_cached_pairs_cpu_ns=0)

    def catalogue(self, digest, text):
        from tools.pipeline_eval.variants import algo08_causal_reuse as installed

        if digest in self.bodies:
            return self.bodies[digest]
        match = self.artifact.rows(digest) if self.artifact is not None else None
        if match is not None:
            count, cached = match
            start = process_time_ns()
            records = installed.parse_element_set_records(text)
            self.counts["strict_reparse_cpu_ns"] += process_time_ns()-start
            start = process_time_ns()
            attached = self.attach(installed.PreparedCatalogue, records, count, cached)
            self.counts["attach_cached_pairs_cpu_ns"] += process_time_ns()-start
            if attached is not None:
                self.counts["sidecar_hit_bodies"] += 1
                self.counts["sidecar_hit_rows"] += count
                self.bodies[digest] = attached
                return attached
            self.counts["invalid_bodies"] += 1
        self.counts["cold_bodies"] += 1
        return super().catalogue(digest, text)

    def attach(self, prepared, records, count, cached):
        if len(records) != count:
            return None
        names, numbers, pairs, epochs, pending = [], [], [], [], {}
        for record, (number, epoch) in zip(records, cached, strict=True):
            if number <= 0 or number != record.satellite_number:
                return None
            lines = record.first_line, record.second_line
            occurrence = pending.get(lines) or self.pairs.get(lines)
            if occurrence is not None:
                pair, previous_number, previous_epoch = occurrence
                if number != previous_number or epoch != previous_epoch:
                    return None
            else:
                pair = lines
                pending[pair] = (pair, number, epoch)
            names.append(record.name)
            numbers.append(number)
            pairs.append(pair)
            epochs.append(epoch)
        self.pairs.update(pending)
        return prepared(tuple(names), tuple(numbers), tuple(pairs), tuple(epochs))
