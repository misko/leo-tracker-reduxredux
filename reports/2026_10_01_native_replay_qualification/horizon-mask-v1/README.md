# Rejected packed horizon representation

The prototype replaced per-satellite prefix counts with a 64-bit interval mask
for up to 65 knots, retaining prefix counts for longer histories. The exact
prototype header is preserved as `horizon_prefix.hpp`; it is **not adopted**.
The working header has been restored to the previously qualified PGO source
hash `ac473e11d684b083366ebbc38718bead676dbb177ffcb663d36d5891e4c82d71`.

Both complete host 400-point traces were exact: fresh native tracks and the
published server-track fixture. Randomized horizon comparisons, NaN/Inf cases,
64-bit boundary cases and the longer-history fallback passed on host and ARM.
ASan/UBSan passed. Expanded long-history tests remain in the component suite
and also pass with the restored prefix implementation.

Two alternating four-trial ARM experiments used the existing 16 heldout search
points. All output scores matched exactly in every trial.

| Comparison | Control mean CPU seconds | Mask mean CPU seconds | Result |
|---|---:|---:|---|
| Previous PGO vs ordinary mask | 12.414778 | 12.874972 | Mask 3.71% slower; compiler-profile confound |
| Ordinary vs ordinary mask | 12.714590 | 12.879680 | Mask 1.30% slower |

`protocol.json` and `ordinary-control-protocol.json` pin the trial orders and
payloads. `comparison.json` and `ordinary-comparison.json` preserve the measured
values. The second experiment removes the PGO confound and supports rejection
of this change. No full ARM scan or concurrent qualification is claimed for
the prototype. The current qualified location binary remains unchanged.
