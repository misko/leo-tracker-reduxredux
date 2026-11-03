# Invalid affinity attempt

The detector exited 127 immediately because this firmware has no `taskset`
executable. Search was then explicitly terminated (exit 143). This is not a
concurrent performance measurement and supplies no detector/science evidence.
The original protocol and execution receipts are retained.

The corrected harness requires a hash-pinned affinity launcher and executes a
bounded affinity preflight before launching either workload. See the separate
`../overlap-affinity-v2/` trial; its results must be evaluated independently.
