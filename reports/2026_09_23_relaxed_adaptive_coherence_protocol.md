# Frozen relaxed adaptive coherence experiment

Use existing IQ from all 301 `scan-hop-28d7592ea614f624` visits with at least one
published passing GLRT candidate in each receiver. No phase or coherence enters
selection. Freeze both metadata bindings before IQ: 331 RX0 anchors and 362 RX1
anchors, independently deduplicated at 5 kHz modulo the pilot-symbol alias.
Do not change the detector, its 0.025 margin gate, or published products.

The weaker rule is **forced opposite-receiver measurement**. Use each native
candidate's epoch and carrier as a template in both receivers. Do not require
the opposite receiver to have retained a matching GLRT candidate, to pass the
nine-sample timing gate, or to independently detect a second source. Preserve
all results, including weak support and failures. Both native-anchor directions
are predeclared sensitivity arms; never choose whichever arm gives a nicer
held result. The two directions are not independent validation datasets.

For each source, use the existing fixed-timing fractional pilot frontend with
symbols 2–65, the bound lower edge, and the prior seed/salt random whole-frame
partition. The native anchor epoch is deliberately shared by both RX. Estimate
per-RX within-frame residual frequency on training frames before summing symbols;
freeze it for held exact, rolled-17, and +37-sample wrong-timing measurements.
There is no timing search or held refit.

Estimate one common raw RX1−RX0 frequency offset per dwell for **all** anchors
and both directions. Use only 512-sample windows lying within training frames
of every anchor, with eight-sample guards. Choose at most 64 non-overlapping
windows at fixed evenly spaced indices, requiring at least three. Demean each
RX/window, multiply RX1 by conjugate RX0, Hann taper, pool 32768-point FFT power,
and refine its maximum by three-bin log-parabolic interpolation. Translate a
native RX0 carrier to RX1 by adding that offset, or native RX1 to RX0 by
subtracting it. Keep failures when common training support is insufficient.

Measure per source: held weighted circular concentration and normalized complex
coherence after a train-only product-rate fit over 120 ms; also six fixed 20 ms
blocks using the same train/held masks and a local training-only rate. Require
at least three train and three held frames per block; retain invalid blocks.
Record exact/rolled and exact/wrong-timing held power separately for each RX.
For descriptive screening, pilot support requires both ratios >2 in both RX;
short-phase screening additionally requires median 20 ms concentration >=0.8
and at least four valid blocks. These are fixed diagnostic screens, not claims
of satellite identity or prospective association performance.

For every source combination within each arm, pair nearest frames within half
a frame period. Compute held source-B-minus-source-A receiver phase **before
separate source-product rate removal**. Restore the known coarse carrier origin
at 60 ms exactly once; this constant affects phase origin, not concentration.
Use geometric-mean source weights; also report unweighted concentration. Require
at least three pairs held by both sources. A fixed wrong-time control circularly
shifts the held B sequence by half its length without refitting. Report its
concentration separately; do not tune a gate to its outcomes. Descriptive DD
screening requires pilot support for both sources and held DD concentration
>=0.8. Report all pairs, rather than selecting the best held pair per dwell.

Compare the original five reference dwell IDs on the same metrics. Their
historical results are an additional reference, not interchangeable data: this
experiment estimates a new common training-only raw offset and uses native
candidate anchors in each arm. Candidate priors came from the same recording's
20 ms GLRT probes, so this remains retrospective conditional analysis.

Read each of the 301 visits once (36.12 seconds of unique IQ), cap the process
at ten minutes per worker, checkpoint every ten visits, and save frame products so figures
and further audits need no repeat IQ read. No new RF collection.

Use four independent processes over interleaved, disjoint visit-index lists.
Each worker opens its own read-only source. This changes computation scheduling
only; each visit retains the same random frame partition and estimators.
