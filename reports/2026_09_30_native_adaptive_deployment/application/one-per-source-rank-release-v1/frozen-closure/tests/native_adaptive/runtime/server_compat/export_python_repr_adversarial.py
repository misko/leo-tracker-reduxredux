#!/usr/bin/env python3
import math
import random
import struct
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: export_python_repr_adversarial.py OUTPUT.tsv")


def bits(value):
    return struct.unpack(">Q", struct.pack(">d", value))[0]


cases = {}


def add(value):
    if math.isfinite(value):
        cases.setdefault(bits(value), repr(value))


for value in (
    0.0,
    -0.0,
    math.ldexp(1.0, -1074),
    -math.ldexp(1.0, -1074),
    math.nextafter(math.ldexp(1.0, -1022), 0.0),
    math.ldexp(1.0, -1022),
    sys.float_info.max,
    -sys.float_info.max,
):
    add(value)

for exponent in range(-1074, 1024):
    value = math.ldexp(1.0, exponent)
    for signed in (value, -value):
        add(math.nextafter(signed, -math.inf))
        add(signed)
        add(math.nextafter(signed, math.inf))

for exponent in range(-323, 309):
    value = float(f"1e{exponent}")
    for signed in (value, -value):
        add(math.nextafter(signed, -math.inf))
        add(signed)
        add(math.nextafter(signed, math.inf))

random_values = 0
generator = random.Random(0x5E71A1)
while random_values < 100_000:
    value = struct.unpack(">d", generator.getrandbits(64).to_bytes(8, "big"))[0]
    if math.isfinite(value):
        add(value)
        random_values += 1

with open(sys.argv[1], "w", encoding="ascii") as output:
    for value_bits, lexeme in cases.items():
        output.write(f"{value_bits:016x}\t{lexeme}\n")

print(f"python repr adversarial fixture: {len(cases)} unique finite binary64 values")
