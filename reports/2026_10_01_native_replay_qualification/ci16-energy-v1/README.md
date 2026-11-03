# Rejected integer-energy preparation experiment

For CI16 and at most 2^22 samples, squared integer energies accumulate exactly
in binary64 after power-of-two normalization. This prototype combines the two
energy additions while preserving raw and normalized samples. Component tests
cover all signed-16 values, both receivers, extrema, zeros and buffer reuse;
host, ARM and sanitizer checks passed.

The isolated ARM control/new/new/control benchmark prepares 50,000 samples
256 times per run. Prefix checksums are identical, but CPU improves by less
than 1%. No whole-detector benefit was established, so the prototype was not
adopted. Its source, binaries and measurements remain here. The independent
input-contract tests remain in the component.
