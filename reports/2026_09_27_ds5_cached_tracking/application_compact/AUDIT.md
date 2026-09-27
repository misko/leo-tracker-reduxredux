# Application GLRT compute audit

This audit is against the current repository application, not the separate native
one-confirmation research profile:

- `src/leo/scanner/detector.py` SHA-256
  `01c21e7b138bc66c84efc341fff94d7938d18ed04ef9961286d4cabe73879270`
- `src/leo/analysis/starlink/pilot_methods.py` SHA-256
  `d6a599d7eb9cb4d6de5f7e6781cb6ea3ce65de422723d94ebfec9ea0a1fa4193`
- `src/leo/analysis/starlink/acquisition.py` SHA-256
  `b4891b7ceb7f60a8d23c7e8127b836159a48aa5a2e2f0245e25ac26bd96d3742`
- `src/leo/analysis/starlink/templates.py` SHA-256
  `7ea6575d681d28796d74ebbd912e423082f7fd792bfc5aa6c42b1bb194788b51`

The default application evaluates 11 overlapping 20 ms probes at 10 ms stride for
each of two receivers.  Every one of those 22 receiver probes calls
`acquire_symbolwise`, then calls `conditioned_glrt64_score` for as many as eight
retained candidates.  A full default dwell can therefore contain 22 blind
acquisitions and 176 conditioned GLRT confirmations.  The native server study's one
selected-window, one-confirmation call is not an application-equivalent baseline.

## Prior measured stage evidence

The pinned August P-core receipt
`reports/figures/2026_08_22_t3_glrt_hardware_execution_alignment/p-core-implemented.json`
measured the same application kernels on one 20 ms Standard probe.  Its median
acquisition was 39.817 ms, complete ten-candidate detector was 54.429 ms, and one
conditioned-correlation workspace was 0.780 ms.  Those are earlier component
measurements, not a new scanner benchmark and not a current end-to-end claim.

The current development profile used ten retained candidates to match that earlier
component configuration, rather than the application default of eight.  Across the
full 11-probe, dual-receiver call it measured 1,558.720 ms CPU at 2.5 Msps and
4,131.688 ms CPU at 5 Msps.  The inclusive acquisition totals were 1,252.281 and
4,164.770 ms; conditioned GLRT-64 totals were 276.775 and 302.717 ms, of which the
workspace accounted for 184.664 and 209.177 ms.  Stage instrumentation has overhead,
so its inclusive totals are diagnostic and are not additive to the uninstrumented
whole-call values.

They establish the priority: even eliminating the conditioned workspace entirely
cannot provide 10x while every receiver/probe still pays for blind acquisition.  The
first useful implementation can remove clear allocation and setup waste, but the
eventual 10x route must reduce the 22 acquisition calls' cost while preserving their
full candidate inventory.

## Reusable work in the current path

1. **Compact the GLRT-only correlation workspace and cache immutable geometry.**
   `conditioned_glrt64_score` requests only symbols 2..65, but
   `_conditioned_correlation_workspace` allocates six 300-column matrices, copies
   300 columns into each of six tuples, and then `select` stacks the requested 64
   columns again.  Each candidate also copies and converts both cached complex64
   pilot frames to complex128 and rebuilds symbol starts, stops, counts, references,
   and template energies.  The report-owned `prototype.py` caches immutable
   rate/edge geometry and builds only the 64 selected columns.  It retains the
   original count grouping, frame order, vector reductions, valid-support prefix,
   exact/control pairing, and existing `_glrt_pair`.  Twenty oracle tests cover
   both rates and edges, random/zero/pilot IQ, truncated support, input immutability,
   and exception types with exact array and score equality.

2. **Transpose the receiver dimension once per dwell.**  In
   `analyze_glrt64_dwell`, `np.ascontiguousarray(values[start:stop, column])` copies
   every overlapping probe.  Materializing one contiguous vector per receiver before
   the probe loop copies the 120 ms dwell once per receiver; each 20 ms probe can then
   be a contiguous view.  This does not alter numerical operations.  It removes
   repeated copying of the 10 ms overlap, although it does not reduce DSP work.

3. **Pair acquisition's final exact/control verification.**  In
   `acquire_symbolwise`, consecutive `normalized_frame_score` calls for exact and
   rolled-control verification use the same epoch, CFO, verify-symbol indexes,
   received samples, received energy, and rotation.  A paired helper can share those
   inputs while keeping the two `np.vdot` calls and their order unchanged.  The
   preceding acquire-symbol score uses a different symbol set and must remain
   separate.

4. **Cache small GLRT geometry only after the above.**  `_glrt_pair_autocorrelation`
   recreates the 512-bin frequency vector and zero packing arrays for every candidate.
   A rate/shape-keyed immutable grid and caller-owned scratch remove small setup and
   allocation costs.  The short transforms and exact/control spectra remain
   candidate-specific.

## Work that cannot be silently reused

- Candidate correlation values depend on both refined epoch and acquired CFO.  NMS
  deliberately retains distinct timing/CFO basins, so reusing one candidate's
  correlations for another changes the statistic.
- Adjacent probes overlap in samples but start half a 20 ms window apart.  Their
  local frame lattice, boundary support, candidate ranking, and history coordinates
  differ.  Reusing an acquisition result across probes would skip measured evidence.
- Acquisition's final normalized scores are scalar reductions over even/odd symbol
  sets.  They do not retain the per-symbol complex correlations required by GLRT-64.
  A future fused final-verification/GLRT kernel is possible, but must prove the old
  reduction order, candidate inventory, scores, CFO, and boundary support.  The
  compact workspace does not make this semantic change.
- The current `_glrt_pair` already selects the summed-autocorrelation backend for 64
  symbols at size 512.  Recommending that prior prototype again would duplicate an
  optimization already in production.

## Next bounded experiment

The actual 11-probe, dual-receiver profile shows that acquisition remains dominant.
Extend the existing native batched
coarse scorer to accept all probe views in one call while returning the exact same
per-probe score maps.  Keep NMS, refinement, the configured confirmation count,
support, and the two-probe decision unchanged.  This is the narrowest architecture
that targets the measured dominant work without relabeling skipped probes as
detections.
