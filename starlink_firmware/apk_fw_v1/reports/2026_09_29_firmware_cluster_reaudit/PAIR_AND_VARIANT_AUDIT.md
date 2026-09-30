# Frozen symbol relations and variant-dependent initialization

This batch rechecks actual DS10 sign relations and executes the two existing
variant firmware table loaders in isolated emulation. It adds no recordings,
new pair search, decoded identity, or assumed software-to-RF coordinate mapping.

## What changed

The seven previously discovered symbol pairs do not provide individually
supported, transferable copy/complement constraints after controlling the
21 pair-by-visit comparisons. A small pooled excess remains exploratory.
Separately, execution confirms that the two PHY variants use different object
offsets even though their loader loops have the same overall structure.

The new machine-readable `local/association-ledger.json` contains **278 entries**:
12 historical regional hierarchies with all 56 pairwise profile comparisons,
seven local sign-pair definitions with all three visit evaluations, and 157
historical public-reference edges plus 102 connected groups. It preserves source
hashes, coordinates, original evidence, scope, ranked interpretations and
falsifiers. Public-reference entries are provenance only: they are not additional
DS7–DS10 observations, and no public IQ was newly analyzed. This is an expanded
ledger, not yet the complete semantic review of the 195 catalogued receipts.

## Frozen local relations

Coordinates below are `(physical OFDM symbol, original FFT bin)`, not software
byte offsets. Each relation is an XOR of recovered real-axis signs. The seven
pairs were selected using 22 RX0 discovery frames from DS10-F010-v1085; their
parities and coordinates are unchanged here.

| Pair | Coordinate A | Coordinate B | XOR |
|---|---|---|---:|
| P1 | (3,515) | (3,520) | 1 |
| P2 | (3,515) | (7,542) | 0 |
| P3 | (3,524) | (3,527) | 0 |
| P4 | (3,540) | (5,549) | 1 |
| P5 | (5,517) | (5,525) | 0 |
| P6 | (5,517) | (5,546) | 1 |
| P7 | (5,520) | (7,546) | 1 |

Evaluation uses RX1's chronological held subset: 23, 9 and 11 qualified frames
from visits v1085, v1150 and v1162 respectively. These excerpts share a session
and a conditional satellite candidate; they are neither verified satellite
identities nor independent orbital passes. Their held data were used in earlier
research, so this is a focused re-audit rather than pristine confirmation.

The relation graph is bipartite. We rotate all coordinates in one partition
together, keeping repeated/shared coordinates and within-part dependencies
intact. Each visit rotates independently. All **23 × 9 × 11 = 2,277** combinations
are enumerated, including the observed zero rotation. Each pair's score is
centered on its complete cyclic mean; the maximum across 21 centered scores
provides the family reference. There is no simulated precision from drawing
thousands of duplicate rotations of nine frames.

![Frozen pair transfer](local/pair-transfer.png)

No individual pair/visit result reaches family p < .05. The smallest is **.333**;
P1 in the discovery visit's held RX1 frames has 86.96% agreement but family
p **.391**. In the other two excerpts P1 agrees only 33.33% and 45.45%.
The average excess across all 21 scores is **4.26 percentage points** with
an unadjusted pooled cyclic rank **.0316**. Adding that pooled score to the
same maximum-score family gives **1.0**. We therefore do not promote the pooled
result into a new stable relation or field claim.

Circular controls assume an appropriate stationary reference along the qualified
frame sequence. Qualified frames have gaps; rotation preserves sequence order
apart from wraparound, not exact physical time intervals or all mode changes.
These finite-reference ranks are sensitivity evidence, not assumption-free
population probabilities. Small held samples also limit power. Failure to
confirm these fixed relations does not rule out mode-dependent coding.

## Firmware evidence and interpretations

The independently executed software prefix writer is LSB-first; ordinary short
and long forms have different widths, and the signaling branch emits an 8-bit
prefix. These are constraints on software serialization. They do not say that
P1–P7 are adjacent code bits, repeated message bits, or SATAddr bits. Interleaving,
scrambling, FEC, placement and polarity between that writer and these RF
coordinates remain unmapped. Same-symbol pairs cancel a common sign inversion
algebraically, but not an arbitrary phase error; cross-symbol pairs need not
cancel symbol-dependent inversion.

Ranked interpretations of the seven relations are: (1) visit-specific waveform
dependence, bias or selection fluctuation; (2) coded redundancy conditional on
an unknown mode or scrambling state; (3) a fixed header copy/complement rule.
The frozen transfer test weakens interpretation 3. It cannot choose among the
causes in interpretation 1 or decode interpretation 2. Firmware field widths
alone do not justify another unrestricted search for parity or bit placement.

The regional profile trees retain their original held-receiver/chronological
comparisons and sample-count controls in the ledger. They describe average
waveform shape, not synchronized message bits. Known T-code mixtures and
observation conditions remain higher-ranked explanations than identity; see
the [resumed identity report](../2026_09_29_identity_resumption/README.md).

## Actual variant-loader execution

`variant_execution.py` loads the existing ARM64 ELF segments and executes each
loader against synthetic object memory and a synthetic MMIO destination. No
hardware is accessed. Tables are read through verified ELF mappings, and every
write's address, width and value is checked against an independent expected
byte sequence.

| Binary | Loader | Destination pointer member | Table size | Repeats |
|---|---:|---:|---:|---:|
| phyfw_v4 | 0x5f2d0 | object+0x1a588 | 512 words | 16 |
| phyfw_catapult | 0x64ad0 | object+0x1a5a0 | 512 words | 16 |

For inputs 0, 1, 2, 3, 4 and 0xffffffff, each variant performs exactly 8,192
consecutive 32-bit writes. Only input 3 selects the alternative table. All
**98,304 writes across 12 cases** match the expected source tables. The first
harness incorrectly reused v4's member offset for catapult; the write-address
assertion caught it. The corrected harness obtains the member from each binary's
actual load instruction, and a regression checks both layouts.

This strengthens the table-selection/copy claim and directly demonstrates that
variant object layouts cannot be transferred unchanged. It does not execute
the CGM microcode, establish a convolutional generator, identify an interleaver,
prove full initialization reachability, or identify the firmware used by any
recorded satellite. Table repetition is not evidence of 16 repeated RF fields.

## Reproduce

Run from the repository root; outputs remain in ignored `local/`:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/pair_family.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
uv run --no-project --with capstone --with pyelftools --with unicorn python reports/2026_09_29_firmware_cluster_reaudit/variant_execution.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib --with capstone --with pyelftools --with unicorn --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit
```

The research component's 11 tests pass, including shared-coordinate cyclic
controls, odd-cycle rejection, variant-dependent pointer layout, prior prefix
execution, ELF mapping and clustering controls. Raw data and golden fixtures
remain unchanged. Full initialization/caller tracing and the remaining
association families remain open under the active investigation.
