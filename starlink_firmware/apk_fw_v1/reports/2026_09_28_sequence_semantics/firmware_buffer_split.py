"""Execute the real buffer splitter with modeled allocation and memcpy helpers."""

import hashlib
import json
import random
import struct
from pathlib import Path

from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
)

BASE = Path(__file__).resolve().parent


def main():
    root = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
    data = (root / "catson-bin--rx_lmac").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    u.mem_map(0, 0x200000)
    u.mem_write(0, data)
    u.mem_map(0x300000, 0x10000)
    u.mem_write(0x17F8B8, struct.pack("<Q", 0x300100))
    original, allocated, owner, payload = 0x301000, 0x302000, 0x303000, 0x304000
    stop = 0x1F0000
    hooks = []

    def helper(uc, address, size, user_data):
        if address == 0xEEE60:
            uc.mem_write(allocated, bytes(128))
            uc.reg_write(UC_ARM64_REG_X0, allocated)
            hooks.append("allocate")
        elif address == 0x21E70:
            dst, src, count = [uc.reg_read(r) for r in
                               (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
            assert count == 128
            uc.mem_write(dst, bytes(uc.mem_read(src, count)))
            hooks.append("memcpy")
        else:
            return
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    u.hook_add(UC_HOOK_CODE, helper, begin=0xEEE60, end=0xEEE60)
    u.hook_add(UC_HOOK_CODE, helper, begin=0x21E70, end=0x21E70)
    rng = random.Random(20260929)
    cases = []
    for _ in range(100):
        total = rng.randrange(2, 1024)
        split = rng.randrange(1, total)
        raw = rng.randbytes(total)
        u.mem_write(original, bytes(128))
        u.mem_write(owner, bytes(32))
        u.mem_write(original + 8, struct.pack("<Q", owner))
        u.mem_write(original + 0x16, struct.pack("<I", total))
        u.mem_write(original + 0x28, struct.pack("<Q", original))
        u.mem_write(original + 0x30, struct.pack("<Q", payload))
        u.mem_write(payload, raw)
        u.reg_write(UC_ARM64_REG_SP, 0x30E000)
        u.reg_write(UC_ARM64_REG_LR, stop)
        for reg, value in zip(
            (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3),
            (1, 2, original, split), strict=True,
        ):
            u.reg_write(reg, value)
        u.emu_start(0xF2580, stop, timeout=100000, count=3000)
        assert u.reg_read(UC_ARM64_REG_PC) == stop
        assert u.reg_read(UC_ARM64_REG_X0) == allocated
        prefix_len = struct.unpack("<I", u.mem_read(original + 0x16, 4))[0]
        suffix_len = struct.unpack("<I", u.mem_read(allocated + 0x16, 4))[0]
        prefix_ptr = struct.unpack("<Q", u.mem_read(original + 0x30, 8))[0]
        suffix_ptr = struct.unpack("<Q", u.mem_read(allocated + 0x30, 8))[0]
        assert (prefix_len, suffix_len) == (split, total - split)
        assert (prefix_ptr, suffix_ptr) == (payload, payload + split)
        assert bytes(u.mem_read(prefix_ptr, prefix_len)) == raw[:split]
        assert bytes(u.mem_read(suffix_ptr, suffix_len)) == raw[split:]
        cases.append(dict(total=total, split=split, prefix=prefix_len, suffix=suffix_len))
    assert hooks.count("allocate") == hooks.count("memcpy") == len(cases)
    output = dict(
        sha256=digest, cases=cases,
        conclusion="Real f2580 preserves original node as prefix and returns suffix "
        "with an advanced data pointer, without modifying payload bytes.",
        limitation="100 synthetic single-node interior splits only. Allocator and "
        "128-byte metadata memcpy modeled; not full receive execution, chained-node "
        "coverage, integrity verification, or an RF decode.",
    )
    (BASE / "local/firmware_buffer_split.json").write_text(json.dumps(output, indent=2) + "\n")
    print(f"Verified {len(cases)} real-firmware interior splits with modeled helpers.")


if __name__ == "__main__":
    main()
