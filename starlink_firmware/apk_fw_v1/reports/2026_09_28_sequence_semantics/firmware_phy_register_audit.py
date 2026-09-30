"""Record bounded PHY setup writes without assigning undocumented semantics."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent


def main():
    source = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--phyfw"
    binary = source.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326"
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = {}
    for lo, hi in [
        (0x5DBA8, 0x5DC00),
        (0x5E0D4, 0x5E12C),
        (0x5E25C, 0x5E298),
        (0x61DC0, 0x62010),
        (0x62208, 0x62220),
        (0x6ABD0, 0x6AC28),
        (0x6ADE0, 0x6AE1C),
    ]:
        for ins in decoder.disasm(binary[lo:hi], lo):
            instructions[ins.address] = (ins.mnemonic, ins.op_str)
    expected = {
        0x5DBA8: ("add", "x8, x20, #4, lsl #12"),
        0x5DBBC: ("add", "x0, x19, #0xc98"),
        0x5DBD4: ("stp", "x9, x8, [x0, #0x10]"),
        0x5E0F4: ("mov", "w3, #0x155b"),
        0x5E0F8: ("movk", "w3, #0x351c, lsl #16"),
        0x5E0FC: ("mov", "w2, #0xe3d"),
        0x5E100: ("movk", "w2, #0x3822, lsl #16"),
        0x5E104: ("mov", "w1, #0x4345"),
        0x5E108: ("str", "w3, [x0, #4]"),
        0x5E110: ("str", "w2, [x0, #8]"),
        0x5E118: ("str", "w1, [x0, #0xc]"),
        0x5E27C: ("mov", "w3, #0x165c"),
        0x5E280: ("movk", "w3, #0x361d, lsl #16"),
        0x5E284: ("mov", "w2, #0xf3e"),
        0x5E288: ("movk", "w2, #0x3923, lsl #16"),
        0x5E28C: ("mov", "w1, #0x4446"),
        0x5E290: ("movk", "w1, #0x61, lsl #16"),
        0x5E294: ("b", "#0x5e108"),
        0x61DD8: ("ldr", "x4, [x4, #0xcb0]"),
        0x61DE4: ("add", "x3, x3, #0x3c"),
        0x61E58: ("add", "x6, x6, #0x658"),
        0x61EA8: ("ldr", "x4, [x4, #0xcb0]"),
        0x61EB4: ("add", "x3, x3, #0x2c"),
        0x61F28: ("add", "x6, x6, #0x6c8"),
        0x61F78: ("ldr", "x4, [x4, #0xcb0]"),
        0x61F84: ("add", "x3, x3, #0x1c"),
        0x61FF8: ("add", "x6, x6, #0x6e0"),
        0x62208: ("ldr", "x6, [x20, #0xcb0]"),
        0x6220C: ("ldr", "w0, [x6, #0x168]"),
        0x62210: ("lsr", "w0, w0, #0x10"),
        0x62214: ("strh", "w0, [x22, #0x16]"),
        0x62218: ("ldr", "w0, [x6, #0x168]"),
        0x6221C: ("strh", "w0, [x22, #0x18]"),
        0x6ABD0: ("ldr", "x2, [x20, #0x5f0]"),
        0x6AC10: ("ldr", "w3, [x2, #0x64]"),
        0x6AC14: ("ldr", "w4, [x20, #0x664]"),
        0x6AC18: ("sub", "w3, w3, w4"),
        0x6AC1C: ("str", "w3, [x19, #0x18]"),
        0x6ADE0: ("add", "x0, x0, #8, lsl #12"),
        0x6ADE8: ("ldr", "x2, [x0, #0x5f0]"),
        0x6AE10: ("ldr", "w1, [x2, #0x64]"),
        0x6AE14: ("str", "w1, [x0, #0x664]"),
    }
    for address, value in expected.items():
        assert instructions[address] == value, hex(address)
    normal = [0x351C155B, 0x38220E3D, 0x4345]
    mode3 = [0x361D165C, 0x39230F3E, 0x614446]
    left = b"".join(v.to_bytes(4, "little") for v in normal)
    right = b"".join(v.to_bytes(4, "little") for v in mode3)
    assert all(right[i] == left[i] + 1 for i in range(10))
    counters = []
    for address, name, word_offset in [
        (0xB0658, "get_rfp_ldpc_codewords", 0x3C),
        (0xB06C8, "get_rfp_ldpc_syn_failed", 0x2C),
        (0xB06E0, "get_rfp_ldpc_corrected", 0x1C),
    ]:
        assert binary[address : binary.index(b"\0", address)].decode() == name
        counters.append(
            dict(
                name=name,
                string_address=hex(address),
                register_offset_formula=f"4 * ({word_offset} + user + 4 * object_word_at_0x2c)",
                operation="Mask register bit31 and add remaining value to caller accumulator",
                accepted_user_range=[0, 3],
            )
        )
    telemetry_fields = []
    tx_metadata = []
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        relocations = {
            r["r_offset"]: r["r_addend"]
            for s in elf.iter_sections()
            if s["sh_type"] == "SHT_RELA"
            for r in s.iter_relocations()
        }
        for entry, name, offset in [
            (0x10E060, "mpp_pdu_cnt", 0x10),
            (0x10E080, "mpp_pdu_payload_bytes", 0x14),
            (0x10E0A0, "mpp_pdu_gmh_meta_bytes", 0x18),
            (0x10E0C0, "mpp_dropped_pdu_cnt", 0x1C),
        ]:
            address = relocations[entry]
            assert binary[address : binary.index(b"\0", address)].decode() == name
            section = next(
                s
                for s in elf.iter_sections()
                if s["sh_addr"] <= entry < s["sh_addr"] + s["sh_size"]
            )
            position = section["sh_offset"] + entry + 8 - section["sh_addr"]
            assert int.from_bytes(binary[position : position + 8], "little") == offset
            tx_metadata.append(
                dict(name=name, structure_offset=hex(offset), metadata_entry=hex(entry))
            )
        for entry, string_address, name, offset, shift in [
            (0x10BDC0, 0xD0958, "header_decoder_error_cnt", 0x16, 16),
            (0x10BDE0, 0xD0978, "mcs_decoder_error_cnt", 0x18, 0),
        ]:
            assert relocations[entry] == string_address
            assert binary[string_address : binary.index(b"\0", string_address)].decode() == name
            section = next(
                s
                for s in elf.iter_sections()
                if s["sh_addr"] <= entry < s["sh_addr"] + s["sh_size"]
            )
            position = section["sh_offset"] + entry + 8 - section["sh_addr"]
            assert int.from_bytes(binary[position : position + 8], "little") == offset
            telemetry_fields.append(
                dict(
                    name=name,
                    metadata_entry=hex(entry),
                    structure_offset=hex(offset),
                    register_offset="0x168",
                    extracted_bits=[shift, shift + 15],
                )
            )
    result = dict(
        source_sha256=digest,
        object_member="0xcb0 = constructor input base + 0x4000",
        offsets=[4, 8, 12],
        ordinary_words=[hex(v) for v in normal],
        mode3_words=[hex(v) for v in mode3],
        ordinary_bytes=list(left),
        mode3_bytes=list(right),
        receive_ldpc_counter_accessors=counters,
        decoder_error_telemetry=telemetry_fields,
        tx_mpp_telemetry_metadata=tx_metadata,
        tx_counter_producer=dict(
            instruction="0x6ac10–0x6ac1c",
            operation="uint32(register_at_member_0x5f0_plus_0x64 - saved_word_0x664)",
            output_offset="0x18",
            baseline_capture="0x6ade0 adjusts object by 0x8000; 0x6ae10/0x6ae14 save same register",
            limitation="Producer identification uses matching adjacent telemetry layout; "
            "complete serialization call chain and hardware byte accounting unverified.",
        ),
        instructions={hex(k): list(v) for k, v in instructions.items()},
        limitation="Static setup writes only; register meaning and field boundaries "
        "unknown. Named LDPC counters establish block use, not header coding. "
        "Byte differences do not establish generators, interleaving, "
        "scrambling, or RF placement. Firmware not executed.",
    )
    (BASE / "local/firmware_phy_register_audit.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "instructions"}, indent=2))


if __name__ == "__main__":
    main()
