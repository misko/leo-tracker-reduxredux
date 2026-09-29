# Wave6 exact dwell lag-product cache

Physical ARM4 results: scalar preparation averages **1007.331 ms/dwell**;
NEON preparation and folding averages **946.907 ms**. Both preserve all
182 candidate objects and recover 119/119 standard hits; both owned units
pass on ARM. The NEON cache still loses to the simpler shared-load three-lag
fold at **908.417 ms** and adds 14.4 MB at 2.5 MS/s. It is not selected.

This prototype starts from sealed Wave5 final v2 and precomputes lag-1,
lag-3, and lag-5 conjugate products over the complete 120 ms dwell for both
receivers.  Each cached value is the same two FP32 multiply pairs and FP32
add/subtract used by the original fold.  Window processing still iterates
frames and samples in the original order, so only product construction moves;
the addition order into each folded bin is unchanged.  Existing per-frame
valid counts prevent a cached product from crossing the 20 ms window tail.

The fused runner begins its outer process-CPU timer before cache allocation
and construction.  It executes all 22 proposal/search rows, then reports the
outer dwell duration divided by 22 as `fused_total`.  Cache allocation,
construction, proposal work, search work, and loop overhead are therefore all
charged once.  Persistent proposal/search workspace setup and JSON emission
remain outside the timer, matching the existing runner convention.

The cache contains six complex FP32 arrays, or 48 bytes per time sample:
14.4 MB at 2.5 MS/s and 57.6 MB at 10 MS/s.  The original CI16 dwell remains
resident separately.

The owned component test checks bitwise equality of complete folded arrays at
all four rates, both receivers, all three lags, all 22 overlapping windows,
all 16 frame boundaries, and signed CI16 extrema.  Host and sanitizer tests
pass, and the ARM targets cross-build.  The full host704 run reproduces all
86,439 sealed final-v2 candidates with zero changed candidates or windows.

Host timing does not support promotion.  Cached proposal folding falls from
14.01 ms to 11.95 ms per row and total proposal work from 29.27 ms to 27.30
ms, but fully charged `fused_total` rises from 87.37 ms to 97.11 ms.  Cache
preparation and allocation contribute roughly 16.6 ms per row beyond the
reported stage sum.  This is host evidence; an ARM measurement, if run, must
be compared with the fused three-lag 908 ms control rather than an older
960 ms baseline.

The ARM fused binary is `builds/arm/fused_wave6_dwell_products_arm`, SHA-256
`0104364d0a8a1584cf782caf06d3ac8f90997dae133663b1738c1ca77edf9451`.
No physical ARM execution was performed.

## V2 NEON cache construction and folding

V1 remains sealed.  `sources-v2`, `builds-v2`, and `build-manifest-v2.json`
add an ARM-only packed path.  Cache construction loads four interleaved
two-receiver base samples once, retains both receivers' FP32 components, then
forms lag-1, lag-3, and lag-5 products from three delayed loads.  Cached folding
loads and adds four complex FP32 products at a time.  Vector lanes correspond
to independent folded bins; frame calls remain sequential, preserving each
bin's addition order.

V2 uses `malloc`, writes every valid product, and initializes only the one,
three, or five inaccessible tail entries for its lag.  It avoids the six full
array zero-fill passes previously imposed by `calloc`.  The same scalar oracle
test is cross-built with NEON enabled, so root should run
`test_proposal_products_arm` before timing the fused binary.

The V2 ARM fused binary SHA-256 is
`5c79f02310a42d5e167dc2c75c43988e555a706f7ee428081b2bec239771e920`;
the ARM exact-fold unit SHA-256 is
`aa2d80d4d22a23d5eb8a2543ad8edcb38502affc5d505a32351e02a0a7956a59`.
