"""Lossless value archive for owned scientific evidence, without pickle.

Each distinct NumPy array is stored once. The typed value tree preserves mapping
order, non-string keys, float bits, tuples and NumPy scalars. Dataclasses become
their explicit field mapping. This is evidence serialization, not executable
checkpointing of Python likelihood objects.
"""

import io
import json
import zipfile
from dataclasses import fields, is_dataclass

import numpy as np

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.contracts.localization_v3 import require_digest


def pack(value, pngs):
    if set(pngs) != set(PLOTS):
        raise ValueError("All eight PNGs required in standalone evidence")
    blobs = {}

    def encode(v):
        if isinstance(v, np.generic) and v.dtype.fields is None and v.dtype.subdtype is None:
            a = np.asarray(v)
            if a.dtype.hasobject:
                raise ValueError("Object scalars cannot be persisted as scientific evidence")
            return ["scalar", a.dtype.str, a.tobytes().hex()]
        if isinstance(v, (np.ndarray, np.generic)):
            a = np.asarray(v)
            if a.dtype.hasobject:
                raise ValueError("Object arrays cannot be persisted as scientific evidence")
            stream = io.BytesIO()
            np.save(stream, a, allow_pickle=False)
            raw = stream.getvalue()
            sha = sha256_digest(raw)
            blobs.setdefault(sha, raw)
            return ["array" if isinstance(v, np.ndarray) else "scalar", sha]
        if is_dataclass(v) and not isinstance(v, type):
            v = {f.name: getattr(v, f.name) for f in fields(v)}
        if isinstance(v, dict):
            return ["map", [[encode(k), encode(item)] for k, item in v.items()]]
        if isinstance(v, (tuple, list)):
            return ["tuple" if isinstance(v, tuple) else "list", [encode(item) for item in v]]
        if isinstance(v, float):
            return ["float", v.hex()]
        if v is None or type(v) in (bool, int, str):
            return v
        raise TypeError("Unsupported scientific evidence type: " + type(v).__name__)

    tree = encode(value)
    figures = {}
    for name in PLOTS:
        data = pngs[name]
        if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG bytes required")
        sha = sha256_digest(data)
        blobs.setdefault(sha, data)
        figures[name] = sha
    header = canonical_json_bytes(dict(schema_version=1, tree=tree, figures=figures))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:

        def write(name, raw, compression):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = compression
            archive.writestr(item, raw, compresslevel=1)

        write("values.json", header, zipfile.ZIP_DEFLATED)
        for sha, raw in sorted(blobs.items()):
            write(sha.split(":", 1)[1], raw, zipfile.ZIP_STORED)
    return output.getvalue()


def unpack(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "values.json" not in names:
            raise ValueError("Duplicate or missing evidence member")
        header = json.loads(archive.read("values.json"))
        if set(header) != {"schema_version", "tree", "figures"} or header["schema_version"] != 1:
            raise ValueError("Unknown evidence archive schema")
        if set(header["figures"]) != set(PLOTS):
            raise ValueError("Incomplete evidence figure inventory")
        seen, arrays = {"values.json"}, {}

        def blob(sha):
            require_digest(sha)
            name = sha.split(":", 1)[1]
            data = archive.read(name)
            if sha256_digest(data) != sha:
                raise ValueError("Evidence blob digest mismatch")
            seen.add(name)
            return data

        def decode(v):
            if v is None or type(v) in (bool, int, str):
                return v
            if isinstance(v, list) and len(v) == 3 and v[0] == "scalar":
                dtype = np.dtype(v[1])
                data = bytes.fromhex(v[2])
                if dtype.hasobject or len(data) != dtype.itemsize:
                    raise ValueError("Invalid inline numerical scalar")
                return np.frombuffer(data, dtype=dtype, count=1)[0]
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("Malformed evidence node")
            kind, payload = v
            if kind in ("array", "scalar"):
                if payload not in arrays:
                    stream = io.BytesIO(blob(payload))
                    a = np.load(stream, allow_pickle=False)
                    if not isinstance(a, np.ndarray) or stream.tell() != len(stream.getbuffer()):
                        raise ValueError("Expected one numerical array")
                    a.setflags(write=False)
                    arrays[payload] = a
                a = arrays[payload]
                if kind == "scalar" and a.ndim != 0:
                    raise ValueError("Scalar evidence must have zero dimensions")
                return a if kind == "array" else a[()]
            if kind == "float":
                return float.fromhex(payload)
            if kind in ("tuple", "list"):
                values = [decode(item) for item in payload]
                return tuple(values) if kind == "tuple" else values
            if kind == "map":
                result = {}
                for pair in payload:
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise ValueError("Malformed evidence mapping")
                    key, value = map(decode, pair)
                    if key in result:
                        raise ValueError("Duplicate evidence mapping key")
                    result[key] = value
                return result
            raise ValueError("Unknown evidence node kind")

        value = decode(header["tree"])
        pngs = {name: blob(header["figures"][name]) for name in PLOTS}
        if any(not data.startswith(b"\x89PNG\r\n\x1a\n") for data in pngs.values()):
            raise ValueError("Invalid evidence PNG")
        if set(names) != seen:
            raise ValueError("Unbound evidence archive member")
        return value, pngs
