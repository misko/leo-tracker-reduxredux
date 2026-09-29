# Wave 6 proposal rank experiment

This isolated prototype starts from the sealed Wave 5 final v2 source.  The
measured ARM proposal rank stage is about 118 ms per dwell.  Its stable radix
sort made four full count-and-move passes (8 bits each).  This variant uses
three stable passes (11, 11, and 10 bits) and returns whichever workspace owns
the sorted result, avoiding a compensating copy.  It preserves the existing
finite-float key, signed-zero canonicalization, ascending-index tie order, and
all downstream proposal and GLRT arithmetic.

The opportunity is one fewer complete traversal of every score/index array.
A 20--30 ms ARM saving is plausible, but the 2048-entry count table has a
larger cache footprint and the result requires hardware measurement.  No
runtime benefit is claimed by this build receipt.

Host and sanitizer component suites passed.  The frozen 704-dwell comparison
processed 15,488 windows and 86,439 candidate entries with zero changed
candidates or windows (`host704/manifest.json`).  This verifies exact proposal
and final-candidate parity; it is not an ARM speed result.

Build all artifacts with `python3 build.py`.  The ARM binary is
`builds/arm/fused_rate_coarse_gate_arm`; it must be run with the same four-argument
interface as the sealed Wave 5 runner: `RATE EXACT CONTROL INPUT_CI16`.

ARM execution command (hardware owner only):

```
builds/arm/fused_rate_coarse_gate_arm RATE EXACT CONTROL INPUT_CI16
```

The ARM fused binary SHA-256 is
`645fa203a90bf461d21e931397eee6e2641123cc78576a03c5880bf787a8e943`;
the ARM rank-test binary is
`42d49e2e1f074c4cf8fd4a3080f56b1ca1ac29a70bcb6935c9403d6a9e62ce10`.
