# The 60-entry configuration table is not the recovered T-code

The adjacent firmware routine's output length matches the recovered 60-bit
T-code length, but its actual behavior does not. Executing the routine confirms
a threshold mask: zeros followed by repeated 6s or 8s. All 59 nonconstant
T-code states differ from every corresponding binary threshold mask, even
allowing circular offset, reversal and complement.

## Actual firmware behavior

In the existing canonical PHY binary, **0x6b6d0–0x6b734** reads the unsigned
threshold from object+0xfc and another discriminator from object+8. It writes
60 little-endian words beginning at object+0x1c0:

```text
output[i] = 0 if i < threshold
            6 otherwise, when object+8 == 1
            8 otherwise, for other discriminator values
```

The transmit configuration path calls this routine at **0x64d14**, immediately
after the 20-entry mask helper. This is a code connection, not a claimed RF
mapping. The meaning of the discriminator at object+8 is not established here.

`sixty_entry_audit.py` executes the original instructions with synthetic RAM.
It tests thresholds 0–61 and 0xffffffff against discriminator values 0, 1 and 2:
**189 cases**, with every output word checked against the independent formula.
Large thresholds yield all zeros; no out-of-range writes are needed to explain
that result. The routine is not reading a sequence seed or received symbols.

## Falsifiable comparison with the existing T-code model

We use the already recovered seed and explicit model `B[k] = 1 XOR S XOR
roll(S, -k)`. No new RF data, firmware-driven bit search or public-IQ analysis
is involved. The narrow hypothesis is that the table directly represents a
T-code state after converting its two values to binary signs, with unknown
polarity, circular offset or direction.

A nonconstant threshold mask has exactly two cyclic sign transitions. The
59 nonconstant T-code states have **22–42**. Transition count is unchanged by
rotation, reversal and complement, immediately contradicting direct identity.
An exhaustive comparison against all distinct contiguous cyclic runs of ones
confirms that the nearest mask is still **at least 11 of 60 bits different**.
This search covers all thresholds and the permitted transformations; it is a
deterministic structural comparison, not a statistical significance test.

Only state 0, which is constant, matches. A constant pattern is shared by many
unrelated mechanisms and supplies no evidence for a generator relationship.
Bit planes of 6 or 8 either produce the same binary threshold pattern or a
constant pattern, so selecting another bit plane does not rescue this direct
interpretation.

## Consequences and limits

The table does not provide an independent explanation of the T-code-derived
word families or their hierarchical relations. Its length must not be used to
label the 60 recovered states as firmware addresses, satellite identifiers or
sequence-counter values.

This rejects direct table-to-sign equivalence under the stated transformations.
It does not exclude an undocumented downstream encoder, a use of these values
as hardware instructions, or a shared hardware function. Those alternatives
need a traced consumer, rather than a broader blind scan of our recordings.
The physical meaning of the table remains unknown.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with capstone --with pyelftools --with unicorn python reports/2026_09_29_firmware_cluster_reaudit/sixty_entry_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib --with capstone --with pyelftools --with unicorn --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit
```

Ignored `local/sixty-entry-audit.json` contains all executed cases, raw-code
evidence, source/method hashes, seed, per-state transition counts and nearest
mask distances. All 15 component tests pass. Recordings, firmware inputs and
golden fixtures remain unchanged.
