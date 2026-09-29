# Wave 7 exact histogram ranker with Cortex-A9 PGO

This workflow combines two independently exact changes: the sealed Wave 7
one-scan integer-key histogram ranker and target-trained GCC profile-guided
optimization.  It does not enable global fast-math or change final GLRT
arithmetic.

The generate and use builds deliberately share the stable source path
`work/arm` and the absolute profile path
`/var/tmp/leo-wave7-hist-pgo-profile`.  GCC names the four expected profiles
`proposal_core.gcda`, `conditioned_czt.gcda`, `fft_full.gcda`, and
`fused_probe.gcda`; `build_pgo.py use` refuses to build unless all four exist
and are nonempty.  Receipts preserve every command and source hash.  The fresh
`test_rank_histograms_arm` is included with the inherited component suites.

Prepare the immutable instrumented build on the host:

```sh
python3 reports/2026_09_29_arm_wave7_hist_pgo/build_pgo.py generate
```

The root hardware runner can then train on exactly the four `arm4-v2`
contexts, retrieve and archive the profiles, rebuild at the identical paths,
run all ARM component binaries, and evaluate the disjoint held-out 32 panel:

```sh
python3 reports/2026_09_29_arm_wave7_hist_pgo/run_training.py
```

The runner refuses to overwrite a local profile directory.  Its held-out
reference excludes all four training contexts.  The completed held-out32
result is 758.592 ms/dwell, with all 1,201 emitted candidate objects identical
to its frozen reference and 904/921 standard hits recovered.  All 11 ARM
component suites from the use build pass; these unit binaries intentionally
omit profile-use flags so missing unit-specific profiles cannot contaminate
their checks.  On the same panel, Wave 6 combined PGO took
776.473 ms/dwell and the Wave 5 reference took 917.633 ms/dwell.  Thus the
histogram-plus-PGO combination is 2.30% faster than combined PGO and 17.33%
faster than Wave 5 on this held-out panel.  `heldout-comparison.json` binds
those summaries, audits, and row streams by SHA-256.  The non-PGO Wave 7
histogram build's 831.795 ms/dwell result uses a different ARM4 panel and is
not used to calculate these reductions.
