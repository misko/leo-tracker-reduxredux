"""Extract and verify actual PHY table-loader instructions in isolated RAM."""
import hashlib
import json
import struct
from fractions import Fraction
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_LR, UC_ARM64_REG_PC

root = Path(__file__).parent
binary = (root / "catson-bin--phyfw").read_bytes()
digest = hashlib.sha256(binary).hexdigest()
assert digest == "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326"
source = 0xAEBA0
words = struct.unpack_from("<512I", binary, source)
uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
uc.mem_map(0, 0x200000)
uc.mem_write(0, binary)
uc.mem_map(0x300000, 0x20000)
obj, destination, stop = 0x300000, 0x310000, 0x1F0000
uc.mem_write(obj + 0x2D0, struct.pack("<Q", source))
uc.mem_write(obj + 0xCE0, struct.pack("<Q", destination))
uc.reg_write(UC_ARM64_REG_X0, obj)
uc.reg_write(UC_ARM64_REG_LR, stop)
writes = []
uc.hook_add(UC_HOOK_MEM_WRITE,
            lambda u, a, address, size, value, data: writes.append((address, size, value)))
uc.emu_start(0x5EDF0, stop, timeout=1000000, count=150000)
assert uc.reg_read(UC_ARM64_REG_PC) == stop
assert uc.reg_read(UC_ARM64_REG_X0) == 0
expected = [words[i ^ 1] for i in range(512)] * 16
assert writes == [(destination + i * 4, 4, value) for i, value in enumerate(expected)]
assert bytes(uc.mem_read(destination, 32768)) == struct.pack("<8192I", *expected)
pairs = list(zip(words[::2], words[1::2]))
assert all(pair == pairs[0] for pair in pairs[133:])
result = {
    "binary_sha256": digest,
    "source_address": hex(source),
    "source_sha256": hashlib.sha256(binary[source:source + 2048]).hexdigest(),
    "loader_address": "0x5edf0",
    "verified_destination_words": len(expected),
    "unique_pairs": len(set(pairs)),
    "entry_zero_duplicate_indices": [i for i, pair in enumerate(pairs) if pair == pairs[0]],
    "pairs": [{"index": i, "first_u32": a, "second_u32": b}
              for i, (a, b) in enumerate(pairs)],
    "limitation": "Verifies CPU loading into modeled RAM, not hardware interpretation or RF encoding.",
}
(root / "phy-modcod-table.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items() if key not in ("pairs", "entry_zero_duplicate_indices")}, indent=2))
print("Entry-zero duplicates:", result["entry_zero_duplicate_indices"])

rx = (root / "catson-bin--rx_lmac").read_bytes()
assert hashlib.sha256(rx).hexdigest() == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
comparisons = []
for address in (0x12FB88, 0x12F328):
    records = []
    for i in range(256):
        field0, n, field8, identifier = struct.unpack_from("<4I", rx, address + 16 * i)
        if n == 0:
            break
        records.append(dict(field0=field0, field4=n, field8=field8, identifier=identifier))
    assert len(records) == 133
    assert sorted(row["identifier"] for row in records) == list(range(133))
    for row in records:
        if row["identifier"]:
            assert pairs[row["identifier"]][0] == (row["field4"] - 1) // 2
    comparisons.append(dict(address=hex(address), nonzero_ids_matching=132, records=records))
result["mac_table_comparisons"] = comparisons
result["mac_binary_sha256"] = hashlib.sha256(rx).hexdigest()
(root / "phy-modcod-table.json").write_text(json.dumps(result, indent=2) + "\n")
print("Both 133-entry MAC tables: all 132 nonzero IDs match first PHY word = ceil(field4 / 2) - 1")

rates = {}
decoded = []
for row in comparisons[0]["records"]:
    identifier = row["identifier"]
    if not identifier:
        continue
    word = pairs[identifier][1]
    coded_length = (word & 0x1FF) * 64
    rate_index = (word >> 9) & 31
    bits_per_symbol = ((word >> 14) & 7) + 1
    bits_per_codeword = ((word >> 17) & 0x3FFF) * 8
    even_symbol_count = word >> 31
    symbols = (coded_length + bits_per_symbol - 1) // bits_per_symbol
    assert symbols == row["field4"]
    assert bits_per_codeword == row["field8"]
    assert even_symbol_count == int(symbols % 2 == 0)
    rate = str(Fraction(bits_per_codeword, coded_length))
    assert rates.setdefault(rate_index, rate) == rate
    decoded.append(dict(identifier=identifier, candidate_coded_length=coded_length,
                        candidate_bits_per_symbol=bits_per_symbol,
                        bits_per_codeword=bits_per_codeword, symbols_per_codeword=symbols,
                        rate_index=rate_index, candidate_rate=rate,
                        even_symbol_count=even_symbol_count))
result["packed_word_inference"] = decoded
result["candidate_rate_index_map"] = rates
result["interpretation_caveat"] = (
    "MAC field labels supported by diagnostics; coded length, bits per symbol, rate, "
    "and flag interpretations inferred from exact table arithmetic, not RF validation. "
    "Entry zero excluded: MAC says 32 bits/114 symbols, PHY duplicates entry 68."
)
(root / "phy-modcod-table.json").write_text(json.dumps(result, indent=2) + "\n")
print("132 packed words match symbol count, bit count, parity, and a consistent rate-index map")
