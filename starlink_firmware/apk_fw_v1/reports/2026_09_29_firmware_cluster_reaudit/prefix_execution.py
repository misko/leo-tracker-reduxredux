"""Independent bounded execution of prefix branches and the real bit writer."""

import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X28,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--tx_lmac"
CONTEXT, BUFFER, STACK, STOP = 0x400000, 0x410000, 0x508000, 0x600000


def machine(binary):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x300000)
    elf = ELFFile(io.BytesIO(binary))
    for segment in elf.iter_segments():
        if segment["p_type"] == "PT_LOAD":
            uc.mem_write(segment["p_vaddr"], segment.data())
    uc.mem_map(CONTEXT, 0x20000)
    uc.mem_map(0x500000, 0x10000)
    uc.mem_map(STOP, 0x1000)
    return uc


def write_bits(uc, value, width, offset, initial):
    uc.mem_write(CONTEXT, struct.pack("<QQIIIII", BUFFER, BUFFER, 4096, offset, 0, 0, initial))
    uc.mem_write(BUFFER, b"\0" * 8)
    for register, v in [(UC_ARM64_REG_X0, CONTEXT), (UC_ARM64_REG_X1, value),
                        (UC_ARM64_REG_X2, width), (UC_ARM64_REG_SP, STACK),
                        (UC_ARM64_REG_X30, STOP)]:
        uc.reg_write(register, v)
    uc.emu_start(0xE1430, STOP, count=300)
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    pending, words = struct.unpack("<II", uc.mem_read(CONTEXT + 0x14, 8))
    cache = struct.unpack("<I", uc.mem_read(CONTEXT + 0x20, 4))[0]
    output = int.from_bytes(uc.mem_read(BUFFER, 4 * words), "little") if words else 0
    return pending, words, output | (cache << (32 * words))


def prefix(uc, mode, long_form, flag, state, length, count):
    uc.mem_write(STACK, b"\0" * 256)
    uc.mem_write(STACK + 0x64, struct.pack("<III", flag, state, count))
    # 0xc134c–0xc1350 initializes this mask: short count has two bits,
    # long count has four. Success at 0xc1348 also implies incoming w5=0.
    uc.mem_write(STACK + 0x80, struct.pack("<H", 0x0F03))
    for register, v in [(UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X20, mode),
                        (UC_ARM64_REG_X22, CONTEXT), (UC_ARM64_REG_X27, long_form),
                        (UC_ARM64_REG_X28, length), (UC_ARM64_REG_X5, 0)]:
        uc.reg_write(register, v)
    def stop_at_writer(engine, address, size, user_data):
        engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop_at_writer, begin=0xE1430, end=0xE1430)
    try:
        # Reusing the writer's translated block can bypass a newly installed
        # narrow hook in this Unicorn build. Invalidate before this entry point.
        uc.ctl_remove_cache(0, 0x300000)
        uc.emu_start(0xC1354, STOP, count=150)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0xE1430
    finally:
        uc.hook_del(hook)
    width = uc.reg_read(UC_ARM64_REG_X2)
    value = uc.reg_read(UC_ARM64_REG_X1) & ((1 << width) - 1)
    return width, value


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    writer_cases = 0
    for width in range(1, 33):
        for offset in range(32):
            value = (0xA59CF013 ^ (width * 0x12345) ^ offset) & 0xFFFFFFFF
            initial = 0x5A59CE13 & ((1 << offset) - 1)
            pending, words, observed = write_bits(uc, value, width, offset, initial)
            expected = initial | ((value & ((1 << width) - 1)) << offset)
            assert (pending, words, observed) == ((offset + width) % 32,
                                                  (offset + width) // 32, expected)
            writer_cases += 1
    cases = []
    for mode in (0, 1):
        for long_form in (0, 1):
            for state in range(4):
                for flag in (0, 1):
                    for length, count in ((0, 0), (17, 5), (63, 15)):
                        width, value = prefix(uc, mode, long_form, flag, state, length, count)
                        if mode == 1:
                            expected_width, expected = 8, 2 | (flag << 2)
                        elif long_form:
                            expected_width = 16
                            expected = ((flag << 2) | 8 | (state << 4)
                                        | (length << 6) | (count << 12))
                        else:
                            expected_width = 8
                            expected = ((flag << 2) | (state << 4) | (count << 6)) & 255
                        assert (width, value) == (expected_width, expected)
                        cases.append(dict(mode=mode, long_form=long_form, state=state,
                            flag=flag, length=length, count=count, width=width, value=value))
    output = dict(source_sha256=hashlib.sha256(binary).hexdigest(), writer_cases=writer_cases,
                  prefix_cases=cases,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Artificial register/context inputs execute real bounded code; "
                  "not proof of full caller reachability, runtime mode distribution, "
                  "or RF mapping.")
    (BASE / "local/prefix-execution.json").write_text(json.dumps(output, indent=2) + "\n")
    print("Writer checks", writer_cases, "prefix checks", len(cases))


if __name__ == "__main__":
    main()
