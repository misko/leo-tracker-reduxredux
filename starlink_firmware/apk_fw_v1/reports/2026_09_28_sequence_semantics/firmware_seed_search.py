"""Search public firmware for literal representations of the observed 60-bit seed."""

import hashlib
import json
from pathlib import Path

SEED = "010010100010010010001000000000001000100000101000001010100010"
BASE = Path(__file__).resolve().parent


def packed_matches(data, bits):
    """Find every MSB-first bitstream occurrence, including unaligned starts."""
    value = int(bits, 2)
    for offset in range(8):
        skip = (8 - offset) % 8
        needle = int(bits[skip : skip + 48], 2).to_bytes(6, "big")
        position = data.find(needle)
        while position >= 0:
            start = position - int(offset != 0)
            size = (offset + len(bits) + 7) // 8
            if start >= 0 and start + size <= len(data):
                window = int.from_bytes(data[start : start + size], "big")
                recovered = (window >> (size * 8 - offset - len(bits))) & ((1 << len(bits)) - 1)
                if recovered == value:
                    yield start, offset
            position = data.find(needle, position + 1)


def main():
    firmware = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
    reverse_byte = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
    patterns = {}
    for direction in (1, -1):
        sequence = SEED[::direction]
        for rotation in range(60):
            rotated = sequence[rotation:] + sequence[:rotation]
            for complement in (False, True):
                bits = "".join(str(int(b) ^ complement) for b in rotated)
                patterns.setdefault(
                    bits, dict(direction=direction, rotation=rotation, complement=complement)
                )
    seen = {}
    rows = []
    for path in sorted(firmware.glob("catson-bin--*")):
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            rows.append(dict(file=path.name, sha256=digest, duplicate_of=seen[digest]))
            continue
        seen[digest] = path.name
        matches = []
        for layout, view in [
            ("packed_msb_first", data),
            ("packed_lsb_first", data.translate(reverse_byte)),
        ]:
            for bits, description in patterns.items():
                for start, offset in packed_matches(view, bits):
                    matches.append(
                        dict(layout=layout, byte_offset=start, bit_offset=offset, **description)
                    )
        for bits, description in patterns.items():
            values = bytes(map(int, bits))
            for layout, needle in [
                ("uint8", values),
                ("uint32_le", b"".join(int(v).to_bytes(4, "little") for v in values)),
                ("uint32_be", b"".join(int(v).to_bytes(4, "big") for v in values)),
            ]:
                position = data.find(needle)
                while position >= 0:
                    matches.append(dict(layout=layout, byte_offset=position, **description))
                    position = data.find(needle, position + 1)
        rows.append(dict(file=path.name, sha256=digest, bytes=len(data), matches=matches))
    result = dict(
        seed=SEED,
        unique_patterns=len(patterns),
        files=rows,
        limitation="Literal seed representations only. Does not exclude generated sequences, "
        "other packing, instruction-encoded constants, FPGA/ASIC logic, or a transformed seed.",
    )
    (BASE / "local/firmware_seed_search.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
