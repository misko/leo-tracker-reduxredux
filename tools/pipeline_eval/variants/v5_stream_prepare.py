"""Decode bound GLRT candidates into narrow rows and release the private input after tracking."""

import hashlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean


class TrackCandidate(NamedTuple):
    candidate_rank: int
    fractional_epoch_offset_samples: float
    fractional_margin: float
    fractional_tracking_cfo_hz: float
    integer_epoch_sample: int
    passed_fractional_margin_gate: bool

    def __getitem__(self, key):
        return getattr(self, key)


CANDIDATE_FIELDS = frozenset(TrackCandidate._fields) | {
    "fractional_control_score",
    "fractional_exact_score",
}
SPACE = re.compile(r"[ \t\r\n]*")


class PrivateNativeDocument(dict):
    """One freshly decoded document consumed by the original graph preparation."""


def project_record(row):
    if isinstance(row, dict) and row.keys() == CANDIDATE_FIELDS:
        return TrackCandidate(*(row[key] for key in TrackCandidate._fields))
    return row


def decode_native(text):
    """Use the standard JSON decoder per probe; narrow only source.probes[].candidates."""
    decode = json.JSONDecoder().raw_decode

    def token(index):
        return SPACE.match(text, index).end()

    def take_sequence(index, closing, take):
        index = token(index + 1)
        values = []
        if text[index : index + 1] == closing:
            return values, index + 1
        while True:
            value, index = take(index)
            values.append(value)
            index = token(index)
            delimiter = text[index : index + 1]
            if delimiter == closing:
                return values, index + 1
            if delimiter != ",":
                raise json.JSONDecodeError("Expected a JSON delimiter", text, index)
            index = token(index + 1)

    def object_at(index, overrides):
        if text[index : index + 1] != "{":
            return decode(text, index)

        def member(start):
            key, end = decode(text, start)
            end = token(end)
            if not isinstance(key, str) or text[end : end + 1] != ":":
                raise json.JSONDecodeError("Expected a JSON member", text, start)
            value, end = overrides.get(key, default)(token(end + 1))
            return (key, value), end

        pairs, end = take_sequence(index, "}", member)
        return dict(pairs), end

    def default(index):
        return decode(text, index)

    def probes_at(index):
        if text[index : index + 1] != "[":
            return default(index)

        def probe(start):
            value, end = default(start)
            if isinstance(value, dict) and isinstance(value.get("candidates"), list):
                value["candidates"] = [project_record(row) for row in value["candidates"]]
            return value, end

        return take_sequence(index, "]", probe)

    def source_at(index):
        return object_at(index, {"probes": probes_at})

    result, end = object_at(token(0), {"source": source_at})
    if token(end) != len(text):
        raise json.JSONDecodeError("Extra data", text, end)
    if not isinstance(result, dict):
        raise ValueError("Native GLRT document must be a JSON object")
    return PrivateNativeDocument(result)


def read_native(record):
    raw = Path(record["path"]).read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Native job input changed: " + record["path"])
    text = raw.decode(json.detect_encoding(raw), "surrogatepass")
    del raw
    return decode_native(text)


def prepare_owned(operation, document, *args, **kwargs):
    prepared = operation(document, *args, **kwargs)
    if type(document) is PrivateNativeDocument:
        document.clear()
    return prepared


@contextmanager
def stream_preparation(native):
    from leo.application import localization_v3
    from leo.operations import localization_v3_job

    read_bound = localization_v3_job.read_bound
    prepare_tracks = localization_v3.prepare_tracks

    def read(record):
        if record == native:
            return read_native(record)
        return read_bound(record)

    def prepare(document, *args, **kwargs):
        return prepare_owned(prepare_tracks, document, *args, **kwargs)

    with (
        patch.object(localization_v3_job, "read_bound", read),
        patch.object(localization_v3, "prepare_tracks", prepare),
    ):
        yield


def worker(request, result, library):
    native = v5_lean._read(request)["job"]["native_input"]
    with stream_preparation(native):
        compact_finish.worker(request, result, library)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
