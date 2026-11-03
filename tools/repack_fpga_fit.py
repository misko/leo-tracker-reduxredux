#!/usr/bin/env python3
"""Offline FPGA-only FIT replacement; never accesses or deploys to a device."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
import struct
import zlib
from pathlib import Path


def identity(data: bytes) -> dict[str, object]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def bit_identity(data: bytes) -> dict[str, str]:
    if data[:13] != bytes.fromhex("00090ff00ff00ff00ff0000001"):
        raise ValueError("expected a complete Xilinx .bit file")
    offset = 13
    fields = {}
    for tag, name in ((b"a", "design"), (b"b", "part"), (b"c", "date"), (b"d", "time")):
        if data[offset : offset + 1] != tag or offset + 3 > len(data):
            raise ValueError("invalid Xilinx bitstream field")
        size = struct.unpack_from(">H", data, offset + 1)[0]
        offset += 3
        value = data[offset : offset + size]
        if not value.endswith(b"\0") or len(value) != size:
            raise ValueError("truncated Xilinx bitstream metadata")
        fields[name] = value[:-1].decode("ascii")
        offset += size
    if data[offset : offset + 1] != b"e" or offset + 5 > len(data):
        raise ValueError("missing Xilinx bitstream payload")
    size = struct.unpack_from(">I", data, offset + 1)[0]
    offset += 5
    if size != len(data) - offset or b"\xaa\x99\x55\x66" not in data[offset : offset + 512]:
        raise ValueError("truncated bitstream payload or missing synchronization word")
    return fields


class Fit:
    """Bounded libfdt adapter: preserve every property outside explicit updates."""

    def __init__(self, data: bytes, capacity: int | None = None):
        if len(data) < 40 or data[:4] != b"\xd0\x0d\xfe\xed":
            raise ValueError("missing FIT/FDT header")
        total = struct.unpack_from(">I", data, 4)[0]
        if not 40 <= total <= min(len(data), 64 * 1024 * 1024):
            raise ValueError("FIT size is truncated or exceeds bound")
        self.original = data[:total]  # QSPI partition padding is excluded.
        library = ctypes.util.find_library("fdt")
        if library is None:
            raise RuntimeError("libfdt is required (device-tree-compiler package)")
        self.lib = ctypes.CDLL(library)
        signatures = {
            "fdt_check_full": ([ctypes.c_void_p, ctypes.c_size_t], ctypes.c_int),
            "fdt_open_into": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_next_node": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
                ctypes.c_int,
            ),
            "fdt_get_path": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int],
                ctypes.c_int,
            ),
            "fdt_first_property_offset": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_next_property_offset": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_get_property_by_offset": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
                ctypes.c_void_p,
            ),
            "fdt_string": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_char_p),
            "fdt_path_offset": ([ctypes.c_void_p, ctypes.c_char_p], ctypes.c_int),
            "fdt_setprop": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int],
                ctypes.c_int,
            ),
            "fdt_pack": ([ctypes.c_void_p], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes = arguments
            function.restype = result
        source = ctypes.create_string_buffer(self.original)
        self.check(self.lib.fdt_check_full(source, total))
        self.buffer = ctypes.create_string_buffer(capacity or total + 4096)
        self.check(self.lib.fdt_open_into(source, self.buffer, len(self.buffer)))

    @staticmethod
    def check(result: int) -> None:
        if result < 0:
            raise ValueError(f"libfdt rejected FIT: {result}")

    def nodes(self) -> dict[str, dict[str, bytes]]:
        result = {}
        depth = ctypes.c_int(0)
        offset = -1
        while True:
            offset = self.lib.fdt_next_node(self.buffer, offset, ctypes.byref(depth))
            if offset == -1 or depth.value < 0:
                break
            self.check(offset)
            path_buffer = ctypes.create_string_buffer(4096)
            self.check(self.lib.fdt_get_path(self.buffer, offset, path_buffer, 4096))
            path = path_buffer.value.decode("ascii")
            if path in result or len(result) >= 4096 or depth.value > 32:
                raise ValueError("duplicate/excessive FIT nodes")
            properties = {}
            prop = self.lib.fdt_first_property_offset(self.buffer, offset)
            while prop != -1:
                self.check(prop)
                size = ctypes.c_int()
                address = self.lib.fdt_get_property_by_offset(self.buffer, prop, ctypes.byref(size))
                if not address or size.value < 0:
                    raise ValueError("invalid FIT property")
                _, length, name_offset = struct.unpack(">III", ctypes.string_at(address, 12))
                name = self.lib.fdt_string(self.buffer, name_offset).decode("ascii")
                if name in properties or length != size.value:
                    raise ValueError("duplicate FIT property or length mismatch")
                properties[name] = ctypes.string_at(address + 12, length)
                prop = self.lib.fdt_next_property_offset(self.buffer, prop)
            result[path] = properties
        return result

    def replace(self, path: str, name: str, value: bytes) -> None:
        offset = self.lib.fdt_path_offset(self.buffer, path.encode("ascii"))
        self.check(offset)
        data = ctypes.create_string_buffer(value)
        self.check(
            self.lib.fdt_setprop(self.buffer, offset, name.encode("ascii"), data, len(value))
        )

    def packed(self) -> bytes:
        self.check(self.lib.fdt_pack(self.buffer))
        total = struct.unpack_from(">I", self.buffer.raw, 4)[0]
        result = self.buffer.raw[:total]
        self.check(self.lib.fdt_check_full(self.buffer, total))
        return result


def repack(partition: bytes, bitstream: bytes) -> tuple[bytes, dict[str, object]]:
    if len(partition) > 64 * 1024 * 1024:
        raise ValueError("source QSPI partition exceeds supported size")
    if not 100 <= len(bitstream) <= 8 * 1024 * 1024:
        raise ValueError("FPGA bitstream size exceeds supported full-image bounds")
    fit = Fit(partition, len(partition) + len(bitstream) + 4096)
    before = fit.nodes()
    path = "/images/fpga@1"
    if (
        path not in before
        or before[path].get("type") != b"fpga\0"
        or before[path].get("compression") != b"none\0"
    ):
        raise ValueError("expected one inline uncompressed fpga@1 image")
    old = before[path].get("data")
    if not old or any("signature" in node for node in before):
        raise ValueError("missing inline FPGA or signed FIT cannot be repacked")
    bit_metadata = bit_identity(bitstream)
    if bit_metadata["part"] != bit_identity(old)["part"]:
        raise ValueError("replacement FPGA part differs from the backed-up image")
    changes = {(path, "data"): bitstream}
    components = {}
    for node, properties in before.items():
        if node.startswith("/images/") and node.count("/") == 2:
            body = properties.get("data")
            if not body or any(
                key in properties for key in ("data-offset", "data-position", "data-size")
            ):
                raise ValueError("all components must have inline data")
            components[node] = identity(body)
        if node.startswith("/images/") and node.count("/") == 3:
            algorithm = properties.get("algo", b"").removesuffix(b"\0").decode("ascii")
            if algorithm not in ("md5", "sha1", "sha256"):
                raise ValueError("unsupported component integrity hash")
            parent = node.rsplit("/", 1)[0]
            body = before[parent]["data"]
            if (
                properties.get("value")
                != hashlib.new(algorithm, body, usedforsecurity=False).digest()
            ):
                raise ValueError("original component hash mismatch")
            if parent == path:
                changes[(node, "value")] = hashlib.new(
                    algorithm, bitstream, usedforsecurity=False
                ).digest()
    if len(changes) < 2:
        raise ValueError("FPGA component has no integrity hash")
    for (node, name), value in changes.items():
        fit.replace(node, name, value)
    packed = fit.packed()
    after = Fit(packed).nodes()
    expected = {node: dict(properties) for node, properties in before.items()}
    for (node, name), value in changes.items():
        expected[node][name] = value
    if after != expected:
        raise ValueError("repacking changed a protected component or FIT property")
    return packed, {
        "schema": "leo.fpga-fit-repack.v1",
        "allowed_operation": "ram-only",
        "hardware_qualified": False,
        "preserved_original_fit_timestamps": True,
        "source_partition": identity(partition),
        "source_fit": identity(fit.original),
        "original_components": components,
        "replacement_fpga": identity(bitstream),
        "replacement_bit_metadata": bit_metadata,
        "candidate_fit": identity(packed),
        "changed_properties": [f"{node}:{name}" for node, name in changes],
        "all_other_fit_properties_preserved": True,
    }


def dfu(fit: bytes) -> bytes:
    suffix = struct.pack("<HHHH3sB", 0xFFFF, 0xB673, 0x0456, 0x0100, b"UFD", 16)
    return fit + suffix + struct.pack("<I", zlib.crc32(fit + suffix) ^ 0xFFFFFFFF)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-qspi", required=True, type=Path)
    parser.add_argument("--bitstream", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.source_qspi.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("source QSPI partition exceeds supported size")
    if args.bitstream.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("FPGA bitstream exceeds supported size")
    fit, manifest = repack(args.source_qspi.read_bytes(), args.bitstream.read_bytes())
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    image = dfu(fit)
    manifest["candidate_dfu"] = identity(image)
    manifest["source_qspi_path"] = str(args.source_qspi.absolute())
    manifest["bitstream_path"] = str(args.bitstream.absolute())
    for name, data in (
        ("firmware.itb", fit),
        ("firmware.dfu", image),
        ("manifest.json", (json.dumps(manifest, indent=2) + "\n").encode()),
    ):
        descriptor = os.open(args.out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
