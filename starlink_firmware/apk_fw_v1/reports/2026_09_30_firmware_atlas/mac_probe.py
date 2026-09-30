"""Bounded MAC reverse engineering; actual ELF instructions, synthetic inputs only."""

import hashlib
import json
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
AUDIT = (BASE.parents[3] / "reports") / "2026_09_29_firmware_cluster_reaudit"
sys.path.insert(0, str(AUDIT))

from parser_gate import call  # noqa: E402
from prefix_execution import CONTEXT, STOP, machine  # noqa: E402
from raw_audit import FIRMWARE, inspect_binary  # noqa: E402
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0  # noqa: E402


def grant_probe():
    """Execute full CEFF0 grant decoder and CEE00 nested decoder, not diagnostics."""
    source = FIRMWARE / "catson-bin--rx_lmac"
    binary = source.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    )
    uc = machine(binary)
    state, buffer, output, count, canary = [CONTEXT + i * 0x1000 for i in range(5)]
    uc.mem_write(0x17F8B8, struct.pack("<Q", canary))
    uc.mem_write(canary, struct.pack("<Q", 0x123456789ABCDEF))
    rows = []
    for remaining in (0, 15, 16, 20, 21, 28, 29, 36, 37, 41, 42, 46, 47, 48, 55, 56, 57):
        for value in (0, (1 << 56) - 1, *(1 << bit for bit in range(56))):
            uc.mem_write(state, bytes(128))
            uc.mem_write(buffer, value.to_bytes(7, "little") + bytes(121))
            uc.mem_write(output, bytes([0xA5]) * 32)
            uc.mem_write(count, struct.pack("<I", remaining))
            call(uc, 0xEA8B0, (state, buffer, 128))
            assert uc.reg_read(UC_ARM64_REG_PC) == STOP
            call(uc, 0xCEFF0, (state, output, count))
            assert uc.reg_read(UC_ARM64_REG_PC) == STOP
            status = uc.reg_read(UC_ARM64_REG_X0)
            widths = (16, 5, 8, 8, 5, 5, 1, 8)
            expected = int.from_bytes(bytes([0xA5]) * 7, "little")
            available, shift = remaining, 0
            for width in widths:
                mask = ((1 << width) - 1) << shift
                expected = (expected & ~mask) | (value & mask)
                if available < width:
                    break
                available -= width
                shift += width
            decoded = int.from_bytes(uc.mem_read(output, 7), "little")
            assert decoded == expected
            assert status == (0 if remaining >= 56 else 27)
            assert struct.unpack("<I", uc.mem_read(count, 4))[0] == available
            assert bytes(uc.mem_read(output + 7, 25)) == bytes([0xA5]) * 25
            rows.append(
                dict(
                    input_hex=value.to_bytes(7, "little").hex(),
                    available_bits=remaining,
                    status=status,
                    output_hex=decoded.to_bytes(7, "little").hex(),
                    remaining_bits=available,
                )
            )
    evidence = inspect_binary(
        source.name,
        [("full_grant_decoder", 0xCEFF0, 0xCF094), ("full_nested_decoder", 0xCEE00, 0xCEFE8)],
    )
    return dict(
        cases=rows,
        source_sha256=hashlib.sha256(binary).hexdigest(),
        evidence=evidence,
        widths=[16, 5, 8, 8, 5, 5, 1, 8],
        limitation="Known synthetic decoded byte streams, not RF bits. Physical "
        "buffer is 128 bytes throughout; logical remaining-count failures can "
        "partially write output. No physical-buffer truncation assay. Bit 47 is "
        "explicitly consumed and retained; meaning unknown.",
    )


# Prototypes are reconstructed AArch64 register interfaces, not recovered C types.
# 'window' explicitly distinguishes in-function slices from callable entries.
SPECS = [
    (
        "rx",
        0xEA8B0,
        "reader_init",
        "status32(reader *x0, const void *x1, size_t x2)",
        "parser_gate.py",
        "function",
        "Initialize a bounded little-endian bit stream.",
    ),
    (
        "rx",
        0xEADA0,
        "read_bits",
        "status32(reader *x0, uint32_t *x1, uint32_t x2)",
        "sysinfo_address_decode.py",
        "function",
        "Reads requested bits into output; executed widths include 1..32.",
    ),
    (
        "rx",
        0xD7990,
        "control_dispatch",
        "status32(message *x0, buffer_wrapper *x1)",
        "sysinfo_dispatch_decode.py",
        "function",
        "Dispatches control bytes; minimum SYSINFO test accepts eight bytes, rejects seven.",
    ),
    (
        "rx",
        0xD6BB0,
        "sysinfo_body_decode",
        "status32(reader *x0, body *x1, uint32_t *remaining_x2)",
        "sysinfo_address_decode.py",
        "function",
        "Minimal body retains full uint32 SATAddr and two uint8 channel values.",
    ),
    (
        "rx",
        0xD3BC0,
        "sysinfo_base_decode",
        "status32(reader *x0, base *x1, uint32_t *remaining_x2)",
        "sysinfo_address_decode.py",
        "function",
        "Address write can precede logical length failure.",
    ),
    (
        "rx",
        0xD90B0,
        "ephemeris_consumer",
        "return_unknown(const packed_ephemeris *x0, expanded_ephemeris *x1)",
        "sysinfo_consumer.py",
        "function",
        "Copies positions, widens float velocities and zero extends first timestamp word.",
    ),
    (
        "rx",
        0xD7F20,
        "variance_decode",
        "double(uint16_t w0) [return d0]",
        "pnt_variance_format.py",
        "function",
        "u=0 => 0; u=0x3c00 => 0.0009765625; u=0xffff => NaN.",
    ),
    (
        "rx",
        0xCEFF0,
        "ulmap_grant_decode",
        "status32(reader *x0, uint8_t out_x1[7], uint32_t *remaining_x2)",
        "mac_probe.py",
        "function",
        "Seven bytes preserve SID16 and packed40; bit47 explicitly decoded, meaning unknown.",
    ),
    (
        "rx",
        0xCEE00,
        "ulmap_packed_decode",
        "status32(reader *x0, uint8_t out_x1[5], uint32_t *remaining_x2)",
        "mac_probe.py",
        "function",
        "Reads widths 5,8,8,5,5,1,8; retains all 40 bits.",
    ),
    (
        "rx",
        0x51B90,
        "grant_validate",
        "bool32(context *x0, grant *x1, uint32_t w2)",
        "grant_identity_context.py",
        "function",
        "Identity subcheck compares context addresses; other gates constrained by harness.",
    ),
    (
        "rx",
        0xC6240,
        "prefix_parse",
        "status32(meta *x0, table *x1, wrapper *x2, reader *x3, header *x4)",
        "parser_gate.py",
        "function",
        "count=0 selects no-entry; feature1 and state nonzero selects table.",
    ),
    (
        "rx",
        0x27168,
        "descriptor_integrity_window",
        "register window; not a callable C prototype",
        "descriptor_integrity.py",
        "window",
        "Descriptor status bits indicate CRC failures; no checksum polynomial recovered.",
    ),
    (
        "tx",
        0xE1430,
        "write_bits",
        "status32(writer *x0, uint32_t w1, uint32_t width_w2)",
        "prefix_execution.py",
        "function",
        "Executed writer uses least-significant-bit-first software serialization.",
    ),
    (
        "tx",
        0xC1BB0,
        "meh_pad_trailer",
        "status32(writer *x0, uint32_t mode_w1, ignored_w2, "
        "uint32_t trailer_w3, uint32_t *bytes_x4)",
        "meh_transmit_trailer.py",
        "function",
        "One-fill alignment then zero checksum reservation; no checksum computed here.",
    ),
    (
        "tx",
        0xE1940,
        "writer_flush",
        "status32(writer *x0, uint8_t preserve_w1)",
        "meh_transmit_trailer.py",
        "function",
        "Flushes cached word; tested preserve=0 leaves reserved checksum zero.",
    ),
    (
        "tx",
        0xE7390,
        "buffer_join",
        "buffer *(uint32_t tag_w0, uint16_t tag_w1, buffer *x2, buffer *x3)",
        "meh_transmit_trailer.py",
        "function",
        "Links buffer metadata; inspected successful path does not calculate CRC.",
    ),
    (
        "tx",
        0x741B8,
        "descriptor_length_window",
        "register window; not a callable C prototype",
        "transmit_descriptor_lengths.py",
        "window",
        "Excludes mode-dependent trailer counts from descriptor lengths.",
    ),
]


def catalog():
    records = []
    for side, address, name, prototype, script, kind, behavior in SPECS:
        source = FIRMWARE / f"catson-bin--{side}_lmac"
        evidence = inspect_binary(source.name, [(name, address, address + 32)])
        raw = source.read_bytes()
        offset = int(evidence["regions"][0]["file_offset"], 16)
        signature = raw[offset : offset + 32]
        variants = []
        for suffix in ("v4", "catapult"):
            variant = FIRMWARE / f"{source.name}_{suffix}"
            data = variant.read_bytes()
            locations, start = [], 0
            while (found := data.find(signature, start)) >= 0:
                locations.append(hex(found))
                start = found + 1
            variants.append(
                dict(
                    binary=variant.name,
                    sha256=hashlib.sha256(data).hexdigest(),
                    exact_32_byte_file_offsets=locations,
                    semantics_transferred=False,
                )
            )
        method = BASE / script if script == "mac_probe.py" else AUDIT / script
        records.append(
            dict(
                binary=source.name,
                sha256=evidence["sha256"],
                address=hex(address),
                analyst_name=name,
                entry_kind=kind,
                prototype=prototype,
                prototype_confidence="partial ABI; analyst inferred; named types opaque",
                behavior=behavior,
                method=str(method.relative_to(ROOT)),
                method_sha256=hashlib.sha256(method.read_bytes()).hexdigest(),
                entry_instructions=evidence["regions"][0],
                variants=variants,
            )
        )
    grant_evidence = inspect_binary("catson-bin--rx_lmac", [
        ("ulmap_grant_decode", 0xCEFF0, 0xCF094),
        ("ulmap_packed_decode", 0xCEE00, 0xCEFE8)])
    edges = [dict(binary="catson-bin--rx_lmac", caller=region["address"],
                  callsite=i["address"], target=i["operands"].removeprefix("#"),
                  evidence="direct BL in complete bounded decoder body")
             for region in grant_evidence["regions"] for i in region["instructions"]
             if i["mnemonic"] == "bl"]
    return dict(
        functions=records, checked_grant_callgraph=edges,
        limitation="Curated high-value entries, not exhaustive. "
        "Exact 32-byte matches are discovery candidates, not variant equivalence. "
        "Address spaces belong to specific binary hashes. Full graph and candidate "
        "function inventory are supplied separately by the atlas inventory.",
    )


if __name__ == "__main__":
    local = BASE / "local"
    local.mkdir(exist_ok=True)
    result = grant_probe()
    (local / "mac-grant-probe.json").write_text(json.dumps(result, indent=2) + "\n")
    (BASE / "mac_functions.json").write_text(json.dumps(catalog(), indent=2) + "\n")
    print("Grant decoder cases:", len(result["cases"]))
