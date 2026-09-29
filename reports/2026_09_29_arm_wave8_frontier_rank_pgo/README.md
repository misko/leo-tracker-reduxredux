# Wave 8 frontier rank PGO

This experiment starts from the sealed Wave 7 frontier PGO source: eight
proposal frames, half proposal FFT grid, minimum-one neighbor tracking, radius
one, and all 16 coarse frames.  It changes only ranking to the exact Wave 7 v2
one-scan digit histograms and integer signed-zero canonicalization.  Proposal
geometry remains approximate; coarse, fine, and final scientific arithmetic is
unchanged.

`build_native.py` produced host and sanitizer builds.  All 12 component suites,
including the fresh histogram test and tracking test, pass in both builds.
Host704 is candidate-exact against `arm_wave7_fullcoarse_radius1/host704`: all
77,894 objects in 15,488 windows are identical, with the same 18,465/19,581
standard-hit recovery.  Host timing is diagnostic and does not predict the
Cortex-A9 result.

The immutable instrumented target build is created with:

```sh
python3 reports/2026_09_29_arm_wave8_frontier_rank_pgo/build_pgo.py generate
```

It uses stable sources at `work/arm`, the unique absolute profile directory
`/var/tmp/leo-wave8-frontier-rank-pgo-profile`, and expects five nonempty files:
`proposal_core.gcda`, `proposal_tracking.gcda`, `conditioned_czt.gcda`,
`fft_full.gcda`, and `fused_probe.gcda`.  The use build refuses incomplete
profiles.  Root can train on the same four contexts, archive the profiles, run
the ARM units, and evaluate the disjoint held-out32 panel with:

```sh
python3 reports/2026_09_29_arm_wave8_frontier_rank_pgo/run_training.py
```

The completed held-out32 target result is 470.056 ms/dwell versus 473.794
ms/dwell for frontier PGO alone (0.79% lower), with the same 854/921 standard
hits recovered.  The exact rank change therefore gives a measured additional
gain on top of PGO, while the detector remains the separately identified
approximate frontier configuration.
