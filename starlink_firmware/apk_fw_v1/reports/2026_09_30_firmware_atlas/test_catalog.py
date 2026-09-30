"""Independent miniature ELF oracle: boundaries, calls, and uncertainty labels."""

import gzip
import json
import struct

from catalog import decode_call, inventory


def miniature_elf(path, include_fde=False):
    # Four instructions at 0x1000: forward BL, indirect call, RET, backward BL.
    text = struct.pack("<IIII", 0x94000003, 0xD63F00A0, 0xD65F03C0, 0x97FFFFFD)
    strings = b"\0first\0second\0"
    names = b"\0.text\0.symtab\0.strtab\0.shstrtab\0.eh_frame\0"
    symbols = bytes(24) + struct.pack("<IBBHQQ", 1, 0x12, 0, 1, 0x1000, 12)
    symbols += struct.pack("<IBBHQQ", 7, 0x12, 0, 1, 0x100C, 4)
    chunks = [text, symbols, strings, names]
    if include_fde:
        # DW_EH_PE_pcrel|sdata4 FDE independently declares [0x1000, 0x1010).
        cie_body = bytes(4) + b"\x01zR\0\x01\x78\x1e\x01\x1b" + bytes(3)
        cie = struct.pack("<I", len(cie_body)) + cie_body
        fde_body = struct.pack("<IiI", len(cie) + 4, 0x1000 - (0x2000 + len(cie) + 8), 16)
        fde_body += bytes(4)
        chunks.append(cie + struct.pack("<I", len(fde_body)) + fde_body + bytes(4))
    offsets = []
    body = bytearray(64)
    for chunk in chunks:
        offsets.append(len(body))
        body.extend(chunk)
    body.extend(bytes((-len(body)) % 8))
    shoff = len(body)
    body.extend(bytes(64))
    section_headers = [
        (1, 1, 6, 0x1000, offsets[0], len(text), 0, 0, 4, 0),
        (7, 2, 0, 0, offsets[1], len(symbols), 3, 1, 8, 24),
        (15, 3, 0, 0, offsets[2], len(strings), 0, 0, 1, 0),
        (23, 3, 0, 0, offsets[3], len(names), 0, 0, 1, 0),
    ]
    if include_fde:
        section_headers.append((names.index(b".eh_frame"), 1, 2, 0x2000,
                                offsets[4], len(chunks[4]), 0, 0, 4, 0))
    for name, kind, flags, addr, offset, size, link, info, align, entsize in section_headers:
        body.extend(struct.pack("<IIQQQQIIQQ", name, kind, flags, addr, offset,
                                size, link, info, align, entsize))
    body[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + bytes(9),
                            2, 183, 1, 0x1000, 0, shoff, 0, 64, 56, 0, 64,
                            len(section_headers) + 1, 4)
    path.write_bytes(body)


def test_branch_sign_extension_and_indirect_registers():
    assert decode_call(0x1000, 0x94000003) == ("bl", 0x100C)
    assert decode_call(0x100C, 0x97FFFFFD) == ("bl", 0x1000)
    assert decode_call(0, 0x96000000) == ("bl", -0x8000000)
    assert decode_call(0, 0xD63F00A0) == ("blr", 5)
    assert decode_call(0, 0xD61F0220) == ("br", 17)
    assert decode_call(0, 0xD65F03C0) is None
    assert decode_call(0, 0x14000001) is None  # tail branch is not a call


def test_miniature_elf_has_known_functions_and_uncertain_types(tmp_path):
    binary = tmp_path / "fixture.elf"
    miniature_elf(binary)
    result = inventory(binary, tmp_path / "out", disassemble=True)
    assert result["function_entries"] == result["metadata_supported_entries"] == 2
    assert result["direct_call_sites"] == 2
    assert result["indirect_call_sites"] == 1
    with gzip.open(result["functions"], "rt") as stream:
        rows = [json.loads(line) for line in stream]
    assert [r["names"] for r in rows] == [["first"], ["second"]]
    assert [r["declared_ranges"][0]["end"] for r in rows] == [0x100C, 0x1010]
    assert all(r["prototype"] is None and r["example_outputs"] is None for r in rows)
    with gzip.open(result["calls"], "rt") as stream:
        calls = [json.loads(line) for line in stream]
    assert [(r["source_candidate"], r["target"]) for r in calls] == [
        (0x1000, 0x100C), (0x1000, None), (0x100C, 0x1000)]
    with gzip.open(result["disassembly"], "rt") as stream:
        assembly = stream.read()
    assert "blr x5" in assembly and "ret" in assembly


def test_stripped_function_targets_are_only_candidates(tmp_path):
    binary = tmp_path / "stripped.elf"
    miniature_elf(binary)
    data = bytearray(binary.read_bytes())
    # Change both function symbols to STT_NOTYPE without changing instructions.
    data[64 + 16 + 24 + 4] = 0x10
    data[64 + 16 + 48 + 4] = 0x10
    binary.write_bytes(data)
    result = inventory(binary, tmp_path / "out")
    assert result["metadata_supported_entries"] == 0
    assert result["function_entries"] == 2
    with gzip.open(result["functions"], "rt") as stream:
        rows = [json.loads(line) for line in stream]
    assert all(r["boundary_confidence"] == "candidate_only" for r in rows)
    assert all(r["declared_ranges"] == [] for r in rows)


def test_other_architecture_is_not_decoded_as_aarch64(tmp_path):
    binary = tmp_path / "other.elf"
    miniature_elf(binary)
    data = bytearray(binary.read_bytes())
    struct.pack_into("<H", data, 18, 62)  # EM_X86_64
    binary.write_bytes(data)
    result = inventory(binary, tmp_path / "out")
    assert result["status"] == "unsupported_machine"
    assert "function_entries" not in result


def test_unwind_range_does_not_silently_replace_symbol_range(tmp_path):
    binary = tmp_path / "fde.elf"
    miniature_elf(binary, include_fde=True)
    result = inventory(binary, tmp_path / "out")
    assert result["warnings"] == []
    with gzip.open(result["functions"], "rt") as stream:
        first = json.loads(next(stream))
    assert {"end": 0x1010, "source": "eh_frame_fde"} in first["declared_ranges"]
    assert {"end": 0x100C, "source": "symbol:.symtab"} in first["declared_ranges"]
    assert first["candidate_extent_end"] == 0x100C
