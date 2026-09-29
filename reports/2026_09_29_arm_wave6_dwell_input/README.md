# Wave6 dwell input reuse

This exact-input prototype starts from the sealed Wave5 final v2 sources.  It
prepares each complete 120 ms, two-receiver CI16 dwell once into three
dwell-owned representations: raw FP64 complex samples, normalized interleaved
FP32 samples, and FP64 received-energy prefixes.  Each of the 22 overlapping
receiver/window searches borrows offset views into those arrays.  The search
workspace retains ownership of its original allocations; its three pointers
are saved, replaced only for the synchronous call, and restored before every
return from the prepared entry point.

The fused runner starts one process-CPU timer immediately before dwell-cache
allocation and preparation.  After all 22 proposal/search calls it reports
that outer duration divided by 22 as every row's `fused_total`.  Thus the
reported mean charges all cache preparation, allocation, proposal, search,
and loop overhead exactly once per dwell.  Persistent search/proposal setup
and output formatting remain outside the timer, matching the existing CLI's
setup convention.  Per-search `total_cpu` excludes the already charged input
preparation.

Every normalized component is an integer divided by `32768`, so every squared
power is an integer multiple of `2^-30`.  At the largest supported input,
`2 * 1,200,000 * 32768^2 = 2,576,980,377,600,000`, below `2^52`.  Consequently
every complete prefix numerator is exactly representable in binary64, and
subtracting two such dyadic values produces the same exact window energy as a
prefix begun at the window boundary.  The owned test exercises full-scale
120 ms inputs, all 22 overlapping views, a partial tail, and all four rates.
The direct-ingest test also compares prepared-view candidates and verifies
pointer restoration.

The cache occupies 64 bytes per time sample across both receivers: 32 bytes
raw FP64 complex, 16 bytes normalized FP32, and 16 bytes of prefixes, plus 16
bytes for the two terminal prefix cells.  This is 19.2 MB at 2.5 MS/s and
76.8 MB at 10 MS/s in decimal units.

Host and sanitizer receipts pass all seven component tests.  `host704`
compares directly with sealed `arm_wave5_final/host704-v2`: all 86,439
candidate entries are identical, with zero changed candidates and zero
changed windows.  Its 92.938 ms mean `fused_total` is host evidence only.

The ARM binary is
`builds/arm/fused_wave6_dwell_input_arm`, SHA-256
`72e09e10bbe28b2b1fe6964e26b051375b7b70e2ac5d7130ffaa3559c37b1e74`.
No physical ARM execution was performed.
