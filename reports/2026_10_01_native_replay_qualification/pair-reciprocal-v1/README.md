# Conservative reciprocal experiment

Reuse a reciprocal across the eleven time offsets within each satellite/track
bound check. Multiply 1/sqrt(2N) by (1 - 2^-48), rounding the lower bound inward
by substantially more than normal double division/multiplication rounding.
The original guarded division helper remains the fallback. Final scoring is
unchanged. Prototype source and its randomized test are preserved here.

Both complete host 400-point traces remain exact. Host research tests,
physical ARM bound tests and ASan/UBSan on the changed inline helper pass
(linked location-library objects were not sanitizer-instrumented).

Matched ordinary O3 ARM control/prototype/prototype/control runs over sixteen
heldout sites preserve every score. Mean CPU changes from 12.565279 to
12.537886 seconds, only 0.22%. This is insufficient evidence of a useful
deployment gain; test moving preparation outside the satellite loop next.
No full ARM search or concurrent-cadence improvement is claimed.
