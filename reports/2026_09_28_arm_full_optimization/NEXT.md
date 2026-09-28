# Next optimization priorities

The measured full-dwell ARM kernel cost is 60.314 CPU seconds per 120 ms of
saved dual-receiver IQ. The 40% headroom objective is not close to satisfied.
Small loop improvements alone are insufficient; the next experiment should
change how acquisition work is reused while retaining explicit per-window hit
accounting.

1. Replay adjacent windows with timing/CFO hypotheses propagated from the
   previous window, evaluating GLRT on every scheduled window and falling back
   to full acquisition when tracking is insufficient. First test within each
   existing 120 ms dwell: the 10 ms window shift is known. Measure startup and
   fallback costs separately; do not infer steady-state performance from a
   warm-only run. Full-sealed original positive-hit identities remain the
   denominator. This could avoid the measured 1.214 s coarse and 0.904 s fine
   work on tracked windows, but its recovery and fallback frequency are unknown.
2. If full search remains necessary, investigate FP32 fine-FFT screening with
   FP64 recomputation around competing maxima before quadratic interpolation.
   The current pruned-FP64 transform gives no useful 2.5 MS/s ARM benefit.
3. Only optimize final GLRT once acquisition is cheaper: it currently consumes
   about 37.5 ms of each 2,741.5 ms window. Dropping final evaluations alone
   would save little total runtime and risks losing required individual hits.

`BASELINE_RANK_DISTRIBUTION.json` quantifies that last risk on all 704 dwells.
Keeping only the first two *already-acquired, verification-ranked* candidates
would retain 59.8% of original positive hits; four would retain 87.3%, and six
95.9%. These are retrospective counts, not tested fast methods. Obtaining that
ranking already requires the expensive acquisition work, so these fractions
must not be presented as proportional end-to-end speedups.

The coarse-FP32 negative-candidate divergence also motivates a small FP64
recheck of competing coarse peaks. It could restore candidate agreement on
near ties, but no such method has been implemented or benchmarked here.
