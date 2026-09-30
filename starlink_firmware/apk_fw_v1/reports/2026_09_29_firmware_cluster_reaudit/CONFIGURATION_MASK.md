# A threshold mask, with a verified register consumer

The next helper in the role-configuration path has now been traced through
its actual consumer. It creates a **20-entry threshold mask** and optionally
reverses it. The consumer packs those entries into hardware registers. This
is a concrete configuration mechanism, but not a recovered interleaver,
scrambler, message field or sequence generator.

## Verified behavior

In the canonical PHY binary, **0x6b590** reads the unsigned word at object+0xfc
and the byte at object+0x100. For a threshold `t`, it builds:

```text
entry[i] = 0 when i < t, otherwise 4, for i = 0..19
reverse all 20 entries when the flag is zero
```

The output occupies object+0x168 through +0x1b7. The apparent vector shuffling
in the disassembly implements this reversal; it is not evidence of a bit
interleaver. A nonzero flag, including 255, takes the unreversed branch.
The scalar-looking `ldr s0` copies integer bits into a SIMD register; the
subsequent `cmhs` comparisons are unsigned integer comparisons, not floating
point thresholding.

The caller at **0x69ec0–0x69ee0** passes this table to **0x6a2d0**. That actual
consumer packs ten 3-bit entries into each of two 32-bit registers, at offsets
0x20 and 0x24 through object member +0x85e0. It preserves the upper two bits
of each register. It also puts a count into the low five bits of a register
through member +0x8600, offset 0x24. For tables produced by this builder, that
count equals `min(t, 20)` regardless of orientation.

When the count is below 20, it sets bit 31 of the first bank's register at
offset 0x1c. When the count is 20, it leaves that bit unchanged; the test's
initial value has it clear. Do not read the latter as a general clearing
operation. The behavior for arbitrary caller-supplied tables is not asserted
by the simple threshold formula.

## Execution and boundaries

`configuration_mask.py` executes both real routines in sequence against
synthetic object/MMIO memory. It verifies thresholds 0–21 and 0xffffffff,
with flags 0, 1 and 255: **69 cases**. Every generated table, packed register,
preserved register bit, count and conditional enable result matches independent
scalar expectations. No hardware or additional recording is used.

The zero-adjustment downlink-role configuration previously traced to threshold
20 therefore produces twenty zeros, independently of orientation. The
zero-adjustment uplink-role threshold 16 produces sixteen zeros and four fours,
with orientation selected by the flag. Runtime arguments can change the
threshold, so these are branch defaults, not measurements of the recorded link.

## Implications for recorded symbols

There is still no verified mapping from these 20 entries to carriers, OFDM
symbols, channel groups or header positions. The mask is generated from
configuration arguments without consuming received message bits. Consequently,
its length and reversal flag do not justify shifting, reversing or dividing
the DS7–DS10 recovered signs into 20 pieces to obtain better clusters.

The nearby caller computes a denominator
`1024 - field_at_0xf4 - 2**(field_at_0xf0 + 1)`, which evaluates to 1004 for
the SAT-TX defaults and 992 for UT-TX defaults. This is exact arithmetic from
the code, not proof of a data-carrier count or a particular null/guard layout.
The numerator also depends on object+0x48. Naming those fields requires tracing
their hardware consumers or obtaining a matching documented definition.

This result excludes an attractive but unsupported interpretation of the SIMD
table operation as coding/interleaving evidence. It adds no satellite identity
feature and supplies no justified new blind RF scan. The neighboring 60-entry
builder is a separate routine; its length alone must not be equated with the
known 60-state T-code.

## Reproduce

```sh
uv run --no-project --with capstone --with pyelftools --with unicorn python reports/2026_09_29_firmware_cluster_reaudit/configuration_mask.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib --with capstone --with pyelftools --with unicorn --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit
```

`local/configuration-mask.json` preserves raw-code evidence, all case results,
and source/method hashes. All 14 component tests pass. Input firmware, recorded
IQ and golden fixtures remain unchanged. The physical semantics of the mask
and its relation, if any, to observed symbol associations remain unresolved.
