# Exclusive work outside the weak all-visit solve and renderer

Use the genuine 808-visit DS30-0016 saved 8 ms packet and the exact corrected
portable orbit and grouped rank publication already verified in
`weak-all8-combined`. The previous saved process placed 1.090 CPU s and
1.116 elapsed s outside its solve and renderer but inside its decision and
publication call. An older 20/12 ms saved route used other solver and image
options, so its import and PNG-decode clocks are context for this run.

Profile one fresh saved process under the shared Gauss flock on CPU2, with
nice 15, I/O priority 7 and one numerical thread. Use the released runtime,
fresh tmpfs output and prepared font-cache option. Retain the existing
published proof, both calibrated fits, owner ordering, grid and path, all
eight independently verified PNGs and all input checks. No waveform
access. Record launch through exit separately from the instrumented
publication phase and audit any additional page-ins.

Measure mutually exclusive CPU and elapsed time for solve, render, first
imports and their full nested work, graph eligibility, scan report views,
hashing, serialized encoding/decoding, file reads, fsync, transaction
writes, manifest and sidecar validation, and independent PNG decode and
pixel hashing. Measure substage counts and the largest import roots.
Graph execution that contributes to the numerical solve remains in the
solve charge. Preserve the ordinary paid solve and render scopes and
test that instrumentation ends before out-of-process output verification.

Reconcile the measured buckets to the original inclusive saved publication
clock. Compare actual input, regional proof, flags, both fits and ordered
owners, grid/path bindings and encoded/decoded figures to the previous
sealed all-visit request before interpreting times. Compare file/cache
counters and identify any unassigned time without treating it as removable.
The one run is a profile, so a wall difference alone is not evidence of a
speedup.

Consider one sound opt-in candidate only if the profile identifies a
repeat of immutable data work with at least 0.100 s exclusive CPU available
in the measured request. Count the applicable subset inside each bucket
and price retained inputs, validation and fallback. Modules loaded once,
the first required verification and exact solve/render evaluations are
outside this duplicate-work estimate.
