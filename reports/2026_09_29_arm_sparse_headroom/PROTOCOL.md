# Exact sparse native GLRT headroom qualification

Target: the maintained native RAM API introduced in commit
`32f71e25b35390a73a5d3a79a222d923b07b40ff`, processing the first 20 ms of
each receiver in a 120 ms dual-RX dwell. There are exactly two receiver-windows.
Window placement, proposal/candidate settings and thresholds stay fixed.
This opt-in native engine remains distinct from the deployed fractional
adaptive detector and live capture worker. No RF collection is authorized.

## Gate frozen before optimization results

Primary rate: **2.5 MS/s**. Qualification covers all 152 existing saved DS7
dwells at that rate, randomized as whole dwells with seed **2026092901**.
Use ten repetitions per dwell for a sustained panel of 1,520 calls per final
variant, and compare identical inputs/template hashes against the unmodified
native numerical behavior. Report first-call/cold-start costs separately but
do not silently remove slow detector calls from the distribution.

The preferred gate is **maximum detector CPU and monotonic wall time <=100 ms**,
with p50/p95/max all reported. This reserves at least 20 ms (16.7% of the dwell)
for scheduling and other work; it is a provisional analysis reserve, not a
measurement of simultaneous capture capacity. A weaker result with p95 <=100 ms
and max <120 ms must be labeled as such, not called the preferred gate. Any
CPU or wall deadline miss is counted. A sample maximum is not a hard real-time
proof. If the gate fails, retain the worst-case identity and measured stage
breakdown and continue ranked, measured optimizations.

## Boundaries

Detector measurements begin immediately before the public RAM API call and
end immediately after it returns, including its allocations, preparation,
proposals, search and cleanup. CPU and wall clocks cover the same boundary.
Also retain the API's original internal CPU interval for comparison with the
published result. Setup/context creation, file input, output serialization,
destruction and whole-process elapsed time are measured separately. Persistent
context setup may be amortized only when explicitly labeled; per-process
saved-file end-to-end timing is never presented as persistent RAM latency.

Profile phase timers and any allocation/FFTW instrumentation are diagnostics.
Nested fine/conditioned/final-scoring counters are not summed as disjoint time.
Instrumentation overhead and instrumented versus normal builds must be
distinguished. Freeze source/compiler/FFTW/profile/binary/input/output hashes.

Compare candidate values exactly, excluding timing/provenance identifiers only.
Also report positive candidate recovery against current native sparse and the
frozen original dense reference, plus unchanged public overlap projection.
Approximation, if tested, must be a separate named variant with explicit losses.
PGO training contexts must be declared; report held-out contexts separately.

## Compatibility and stability

Check every supported rate (2.5/5/7.5/10 MS/s), dwell (120/240/360 ms), and stride
geometry with component tests. The 20 ms-stride mode is a compatibility check,
not the primary optimization workload. Reuse the prior mixed-rate saved panel
for spot checks. Record RSS, device memory, CPU pinning, thermal/frequency
interfaces if available, and repeated-run distributions. Do not infer a stable
temperature from an absent sensor. Preserve the known 10 MS/s × 360 ms memory
qualification limit unless new physical evidence resolves it.

Saved files feed RAM; no radio collection or concurrent real capture is part
of these measurements. Any simulated load must be separately labeled and may
not qualify DMA/capture throughput or losslessness.

## Declared compiler-training amendment before PGO v3

The random 32-context compiler training omitted the measured clipped-grid
outlier. PGO v2 reduced typical latency but regressed that tail relative to
the same source without PGO. A separate **tail-aware PGO v3** experiment adds
`scan-fw-319730ab74ce43e7`, visit 138, to those 32 contexts: **33 training and
119 compiler-held-out contexts**. The timing panel, ten repeats, candidate
settings, exactness authority and 100-ms headroom gate do not change. The
added case is explicitly training data; it must not be described as held out.
This amendment tunes compiler coverage only, not detector thresholds or
scientific parameters. The original 32-context profiles and their results
remain retained and separately labeled.
