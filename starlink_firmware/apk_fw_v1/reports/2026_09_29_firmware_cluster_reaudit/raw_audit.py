"""Fresh ELF-mapped instruction evidence and saved-association artifact inventory."""

import hashlib
import io
import json
import re
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
FIRMWARE = ROOT / "starlink_firmware/apk_fw_v1/local/firmware"


def file_offset(segments, address, length):
    matches = [s["offset"] + address - s["address"] for s in segments
               if s["address"] <= address and address + length <= s["address"] + s["filesz"]]
    if len(matches) != 1:
        raise ValueError("Address is not uniquely backed by file bytes")
    return matches[0]


def inspect_binary(name, windows):
    path = FIRMWARE / name
    binary = path.read_bytes()
    elf = ELFFile(io.BytesIO(binary))
    assert elf["e_machine"] == "EM_AARCH64" and elf.little_endian
    segments = [dict(address=int(s["p_vaddr"]), offset=int(s["p_offset"]),
                     filesz=int(s["p_filesz"]), memsz=int(s["p_memsz"]), flags=int(s["p_flags"]))
                for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    regions = []
    for label, start, end in windows:
        offset = file_offset(segments, start, end - start)
        code = binary[offset:offset + end - start]
        instructions = [dict(address=hex(i.address), mnemonic=i.mnemonic, operands=i.op_str)
                        for i in decoder.disasm(code, start)]
        assert len(instructions) * 4 == len(code)
        regions.append(dict(label=label, address=hex(start), file_offset=hex(offset),
                            sha256=hashlib.sha256(code).hexdigest(), instructions=instructions))
    strings = []
    for match in re.finditer(rb"[\x20-\x7e]{8,}", binary):
        value = match.group().decode("ascii")
        if re.search(r"scrambl|interleav|pdu.seq|header.decoder|sataddr|cgm", value, re.I):
            strings.append(dict(file_offset=hex(match.start()), text=value))
    return dict(path=str(path), sha256=hashlib.sha256(binary).hexdigest(),
                little_endian=elf.little_endian, entry=hex(elf["e_entry"]),
                segments=segments, regions=regions, diagnostic_strings=strings,
                limitation="Bounded static instructions; strings alone do not prove "
                "code reachability.")


def main():
    out = BASE / "local"
    out.mkdir(exist_ok=True)
    specs = {
        "catson-bin--tx_lmac": [
            ("prefix_initialization", 0xC1330, 0xC1354),
            ("prefix_pack", 0xC1354, 0xC13E4),
            ("signaling_branch", 0xC159C, 0xC15EC),
            ("bit_writer", 0xE1430, 0xE15C0),
            ("sequence_branch", 0x7DD5C, 0x7DDE0)],
        "catson-bin--rx_lmac": [("receive_descriptor", 0x27120, 0x27240)],
        "catson-bin--phyfw": [("setup_constants", 0x5E0D4, 0x5E12C),
                              ("mode3_constants", 0x5E25C, 0x5E298),
                              ("error_counter_read", 0x62208, 0x62220)],
        "catson-bin--phyfw_v4": [("CGM_loader", 0x5F2D0, 0x5F330)],
        "catson-bin--phyfw_catapult": [("CGM_loader", 0x64AD0, 0x64B30)],
    }
    binaries = [inspect_binary(name, windows) for name, windows in specs.items()]
    folders = ["2026_09_28_signal_clustering", "2026_09_28_sequence_semantics",
               "2026_09_29_all_track_symbols", "2026_09_29_ds10_signal_extension",
               "2026_09_29_identity_resumption"]
    catalog = []
    for folder in folders:
        root = (BASE.parents[3] / "reports") / folder / "local"
        paths = list(root.glob("*.json")) + list((root / "clusters").glob("*/summary.json"))
        # These nested experiment directories were absent from the first catalog.
        for child in root.iterdir():
            if child.is_dir() and any(token in child.name for token in (
                    "tile", "revisit", "within-visit", "bandwidth", "paired")):
                paths.extend(child.rglob("*.json"))
        for path in sorted(set(paths)):
            if re.fullmatch(r"S\d+\.json", path.name):
                continue
            raw = path.read_bytes()
            value = json.loads(raw)
            catalog.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                                keys=list(value) if isinstance(value, dict) else ["list"],
                                entries=len(value),
                                linkage_files=[str(p) for p in path.parent.glob("*linkage*.npy")]))
    result = dict(binaries=binaries, association_artifacts=catalog,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  inventory_scope="Top-level JSON receipts in five research stages, all-track "
                  "cluster summaries, and nested tile/revisit/within-visit/bandwidth/paired "
                  "experiments. Artifact catalog; semantic association ledger remains in progress.")
    (out / "raw-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Binaries", len(binaries), "association receipts", len(catalog))
    for b in binaries:
        print(Path(b["path"]).name, b["sha256"], "diagnostics", len(b["diagnostic_strings"]))


if __name__ == "__main__":
    main()
