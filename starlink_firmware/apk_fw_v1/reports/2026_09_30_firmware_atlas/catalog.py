"""Static ELF atlas. Candidate boundaries and unknown types remain explicitly unknown.

No firmware is executed. BL targets found by aligned scanning can be embedded data;
they are candidates, not proof of functions. Direct edges exclude tail calls, and
indirect targets are unresolved. FDE ranges are unwind ranges, not guaranteed
source-language functions. Use --disassemble for compressed executable-section text.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import struct
from pathlib import Path

from elftools.dwarf.callframe import FDE
from elftools.elf.elffile import ELFFile


def decode_call(pc: int, word: int):
    if word & 0xFC000000 == 0x94000000:
        immediate = word & 0x03FFFFFF
        if immediate & 0x02000000:
            immediate -= 0x04000000
        return "bl", pc + immediate * 4
    if word & 0xFFFFFC1F == 0xD63F0000:
        return "blr", (word >> 5) & 31
    if word & 0xFFFFFC1F == 0xD61F0000:
        return "br", (word >> 5) & 31
    return None


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def inventory(path: Path, out: Path, disassemble=False):
    out.mkdir(parents=True, exist_ok=True)
    digest = sha256(path)
    prefix = path.name + "-" + digest[:12]
    functions = {}
    warnings = []
    calls = []
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_machine"] != "EM_AARCH64" or not elf.little_endian:
            return {"path": str(path), "sha256": digest, "status": "unsupported_machine",
                    "machine": elf["e_machine"]}
        sections = [(s.name, int(s["sh_addr"]), s.data()) for s in elf.iter_sections()
                    if s["sh_flags"] & 4 and s["sh_type"] != "SHT_NOBITS" and s["sh_size"]]
        if not sections:
            sections = [(f"PT_LOAD_{i}", int(s["p_vaddr"]), s.data())
                        for i, s in enumerate(elf.iter_segments())
                        if s["p_type"] == "PT_LOAD" and s["p_flags"] & 1]
            warnings.append("No executable sections: executable segments used; may include data.")

        def containing(address):
            return next(((name, start, len(data)) for name, start, data in sections
                         if start <= address < start + len(data)), None)

        def add(address, provenance, size=0, name=None):
            if not containing(address):
                return
            row = functions.setdefault(address, {"address": address, "names": [],
                "evidence": [], "declared_ranges": [], "prototype": None,
                "prototype_status": "unknown; ABI register usage is not a C prototype",
                "example_inputs": None, "example_outputs": None,
                "example_status": "not executed or inferred by this catalog"})
            if provenance not in row["evidence"]:
                row["evidence"].append(provenance)
            if name and name not in row["names"]:
                row["names"].append(name)
            if size:
                item = {"end": address + size, "source": provenance}
                if item not in row["declared_ranges"]:
                    row["declared_ranges"].append(item)

        for section in elf.iter_sections():
            if section["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
                continue
            for symbol in section.iter_symbols():
                if symbol["st_info"]["type"] == "STT_FUNC" and symbol["st_shndx"] != "SHN_UNDEF":
                    add(int(symbol["st_value"]), "symbol:" + section.name,
                        int(symbol["st_size"]), symbol.name)
        if elf.get_section_by_name(".eh_frame") is not None:
            try:
                for entry in elf.get_dwarf_info().EH_CFI_entries():
                    if isinstance(entry, FDE):
                        add(int(entry["initial_location"]), "eh_frame_fde",
                            int(entry["address_range"]))
            except Exception as error:
                warnings.append(f"FDE parsing incomplete: {type(error).__name__}: {error}")
        if elf.get_section_by_name(".gopclntab") is not None:
            from go_functions import recover_go_functions

            for entry in recover_go_functions(elf):
                add(entry["address"], "go_pclntab", entry["end"] - entry["address"],
                    entry["name"])
        if elf["e_entry"]:
            add(int(elf["e_entry"]), "elf_entry")
        for name, base, data in sections:
            offset = (-base) % 4
            aligned_end = len(data) - ((len(data) - offset) % 4)
            for index, (word,) in enumerate(struct.iter_unpack("<I", data[offset:aligned_end])):
                pc = base + offset + 4 * index
                decoded = decode_call(pc, word)
                if decoded is None:
                    continue
                kind, target = decoded
                edge = {"site": pc, "kind": kind, "section": name,
                        "instruction_evidence": "aligned executable scan; embedded data possible"}
                if kind == "bl":
                    edge["target"] = target
                    edge["target_in_executable_range"] = containing(target) is not None
                    add(target, "direct_bl_target_candidate")
                else:
                    edge["target_register"] = f"x{target}"
                    edge["target"] = None
                calls.append(edge)

        addresses = sorted(functions)
        for i, address in enumerate(addresses):
            row = functions[address]
            section_name, start, size = containing(address)
            next_start = addresses[i + 1] if i + 1 < len(addresses) else start + size
            row["section"] = section_name
            row["candidate_extent_end"] = min(next_start, start + size)
            row["candidate_extent_status"] = "heuristic next entry; not a proved function end"
            row["boundary_confidence"] = ("metadata_supported" if row["declared_ranges"]
                                          else "candidate_only")
        for edge in calls:
            index = bisect.bisect_right(addresses, edge["site"]) - 1
            row = functions[addresses[index]] if index >= 0 else None
            owns = (row and edge["site"] < row["candidate_extent_end"]
                    and row["section"] == edge["section"])
            edge["source_candidate"] = row["address"] if owns else None
            edge["source_assignment"] = "heuristic candidate partition" if owns else "unassigned"

        if disassemble:
            from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs
            decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
            decoder.skipdata = True
            with gzip.open(out / (prefix + ".asm.gz"), "wt") as output:
                for name, base, data in sections:
                    output.write(f"\n# {name}; executable bytes may include data\n")
                    for offset in range(0, len(data), 65536):
                        instructions = decoder.disasm_lite(
                            data[offset:offset + 65536], base + offset)
                        for address, _size, mnemonic, operands in instructions:
                            output.write(f"{address:016x}: {mnemonic} {operands}\n")

    function_path = out / (prefix + ".functions.jsonl.gz")
    call_path = out / (prefix + ".calls.jsonl.gz")
    outputs = ((function_path, (functions[a] for a in addresses)), (call_path, calls))
    for output_path, rows in outputs:
        with gzip.open(output_path, "wt") as output:
            for row in rows:
                output.write(json.dumps(row, sort_keys=True) + "\n")
    return {"path": str(path), "sha256": digest, "status": "catalogued",
            "executable_bytes": sum(len(d) for _, _, d in sections),
            "function_entries": len(functions),
            "metadata_supported_entries": sum(r["boundary_confidence"] == "metadata_supported"
                                               for r in functions.values()),
            "direct_call_sites": sum(c["kind"] == "bl" for c in calls),
            "indirect_call_sites": sum(c["kind"] == "blr" for c in calls),
            "indirect_branch_sites": sum(c["kind"] == "br" for c in calls),
            "functions": str(function_path), "calls": str(call_path),
            "disassembly": str(out / (prefix + ".asm.gz")) if disassemble else None,
            "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binaries", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disassemble", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    methods = {"method_sha256": sha256(Path(__file__))}
    go_method = Path(__file__).with_name("go_functions.py")
    if go_method.exists():
        methods["go_recovery_method_sha256"] = sha256(go_method)
    for path in sorted(args.binaries.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        result = inventory(path, args.output, args.disassemble)
        summaries.append(result)
        print(json.dumps(result), flush=True)
        (args.output / "summary.json").write_text(json.dumps({
            **methods, "binaries": summaries,
            "complete_run": False}, indent=2) + "\n")
    (args.output / "summary.json").write_text(json.dumps({
        **methods, "binaries": summaries,
        "complete_run": True}, indent=2) + "\n")


if __name__ == "__main__":
    main()
