# Wave5 disjoint phase profile

This is an instrumentation-only copy of the sealed
`arm_direct_ci16_ingest/builds-v3` host source snapshot.  It adds process CPU
timers and emits them from the unchanged fused CLI.  It does not change a
scientific branch, threshold, loop order, candidate field, or input path.

The following `timings_ms` fields are disjoint and sum to `total_cpu` (apart
from the reported residual itself):

- `ingest`: stride-four signed CI16 to the persistent FP64 workspace;
- `coarse`: the complete coarse grid call;
- `peak_scan`: peak allocation and the 11-by-epoch local-maximum scan;
- `peak_retain`: deterministic retention plus release of the scan inventory;
- `fine_cache_setup`: fine FFT cache initialization only;
- `acquisition`: the retained-candidate loop, ordering, cache counters, and
  cache teardown after setup;
- `final_loop`: cached final GLRT and any boundary fallback over candidates;
- `misc`: measured `total_cpu` minus the preceding seven phases, covering
  result setup, phase transitions, and timer/accounting overhead.

The older `fine_fft` and `verification` fields are nested inside `acquisition`.
`glrt` is nested inside `final_loop`. The `conditioned` counter can span
acquisition and boundary fallback; in this mode the measured conditioned work
is inside `final_loop`. These counters must not be added to the disjoint phase sum. Proposal timings remain outside
search `total_cpu`; `fused_total` contains proposal and search.

`build.py` builds host, sanitizer, and Cortex-A9 targets from the owned source
snapshot.  Host and sanitizer unit receipts pass all five inherited component
tests.  The direct-ingest test additionally checks timer accounting on every
supported rate, including the nesting inequalities.

For scientific parity, `host32-base` was generated with the sealed v3 host
binary on the same DS7 regional32 panel.  `host32-profile` uses that output as
its direct reference and reports 3,695 candidate entries, zero changed
candidates, zero changed windows, and `scientific_outputs_identical: true`.
The host timing values establish timer coverage only; they are not ARM speed
evidence.

Root can execute the ARM profile serially with:

```sh
reports/2026_09_29_arm_wave5_profile/builds/arm/fused_wave5_profile_arm \
  RATE EXACT_TEMPLATE CONTROL_TEMPLATE INPUT_CI16
```

The ARM fused binary SHA-256 is
`e5bca5822f770b0d2639ba845bbb67fd8d3da2a31ee1d4d66daaf36ca087c1fd`.
The subsequent root-owned `arm4` physical run preserves all candidate objects
and measures these mean CPU milliseconds per dwell: ingestion 53.639, coarse
220.487, peak scan 44.293, peak retention 2.435, fine-cache setup 8.852,
acquisition 77.366, final loop 190.497, residual 0.953. Proposal generation
adds 460.858, and the measured outer total is 1,060.673 ms. Instrumentation
adds overhead, so use the uninstrumented counterpart for headline performance.
