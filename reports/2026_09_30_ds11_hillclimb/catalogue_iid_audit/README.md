# Exact-IID full-catalogue numerator pilot

The bounded DS11 pilot completed all 12 predeclared cases: the first three
lexicographic bank-eligible tracks in original-plan indices 0 and 1, each at
configured center `(0, 0, 0)` and its scan's saved original-IID endpoint.
Index 1 was fixed before execution because its exporter's training-only anchor
proxy was the lowest among the original 32 scans.  No held value, reference
coordinate, or geographic error selected a case.

All 12 cases retained the leading full-catalogue physical NORAD and retained
numerator mass rounded to exactly 1.0 in floating-point arithmetic.  The
largest omitted likelihood fraction was `exp(-132.551131253439)`, approximately
`2.72e-58`.  This bound applies only to the six selected tracks and two tested
settings per track.  It does not establish continuous-region or all-track DS11
shortlist completeness.

Full-catalogue visibility ranged from 469 to 501 candidates, while 11 to 17
visible candidates were retained.  Every retained prediction replayed the
frozen bank with zero-Hz discrepancy and every visibility mask matched.  The
off-grid IID endpoints used the same bracketing quarter-second state nodes and
linear position/velocity interpolation as the baseline: `[0, 0.25]` seconds
with weight `0.6297335075` for index 0 and `[-1, -0.75]` seconds with weight
`0.5258384443` for index 1.  Candidate CFOs and training likelihoods used the
original fast multi-root Student-t4/100-Hz profiler and 1-MHz CFO penalty.  The
profiler's training return alone entered the comparison.

The numerical results completed in 6.17 and 6.77 seconds, respectively, under
sequential 90-second caps and one BLAS thread.  Five component tests passed,
covering off-grid interpolation, retained numerator mass and leader mapping,
the actual multi-root profiler, and the strict replay guard.  No position fit,
IQ read, new RF, reference-coordinate evaluation, or archive mutation occurred.

The first parent batch wrapper exited 1 after the successful index-0 child had
created its run directory as root; the unprivileged parent could not write the
receipt there.  The completed index-0 result and all six case files were
preserved, and index 0 was not retried.  The failure is recorded in
`attempts/batch-01.receipt.json`; `terminal_receipts/00.recovered.json` binds
the complete result as terminal evidence.  Index 1 was then run once under the
same frozen code and limits, with its exact terminal receipt preserved at
`terminal_receipts/01.json`.

