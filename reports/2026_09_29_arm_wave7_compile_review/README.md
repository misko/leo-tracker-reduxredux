# Wave 7 compiler and layout review

This bounded review starts from the sealed Wave 7 exact histogram-rank source.
It found one safe source-level alias opportunity: the proposal resampling and
folding kernels operate on distinct workspace allocations, and the three lag
outputs are distinct arrays.  `sources-restrict/proposal_core.c` records those
facts with `restrict`; no arithmetic or scientific constants change.

`python3 build.py` produced immutable host, sanitizer, and Cortex-A9 cross
builds in `builds-restrict`.  The component suites passed on host and under
sanitizers.  `host704-restrict` is candidate-exact against the sealed Wave 7
histogram control: 86,439 objects over 15,488 windows with zero changed
objects.  The ARM executable and `.text` hashes differ from control, proving
that the annotation affected generated code, but host timing did not show a
benefit (91.079 ms/dwell fused versus 82.238 ms/dwell control).  This remains
an ARM measurement candidate, not a claimed optimization.

The subsequent physical ARM4 check takes 832.480 ms/dwell versus the matched
831.795 ms histogram/key control. All 182 candidate objects and 119/119
standard hits remain unchanged; ten ARM component suites pass. It therefore
shows no useful ARM gain and is excluded from the preferred combination.

No second alignment variant was justified.  The hot NEON paths already use
unaligned `vld`/`vst` operations, while the target FFTW allocation observed in
earlier experiments provided only 8-byte alignment.  Promising stronger
alignment would therefore require allocator/layout changes and setup-cost
measurement rather than a truthful compiler hint.  Prior work already covered
LTO, strict aliasing flags, loop unrolling, planner modes, limited complex
range, fast-math audits, and Cortex-A9 PGO.  The remaining high-confidence
compiler combination is the exact histogram ranker with target-trained PGO;
that workflow is isolated in `../2026_09_29_arm_wave7_hist_pgo`.
