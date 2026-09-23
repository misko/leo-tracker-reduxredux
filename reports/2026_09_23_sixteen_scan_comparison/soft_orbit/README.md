# Hard/soft identity and orbit feasibility

`final/results.json` is the bounded five-location comparison using the exact
saved randomized masks, all 553 tracks and 14,043 observations.  Each scan's
candidate universe is the union of its published Sacramento and Reno production
winners.  It is therefore prior-conditioned sensitivity evidence, not a blind
catalogue result.

The hard method chooses candidate and integer-second timing shift from training
rows.  The soft method marginalizes the same candidate/timing grid with fixed,
candidate-count-normalized priors and a null component.  Track objectives are
first normalized by training-row count, then weighted by occupied one-second
bins, so dense frequency samples do not become independent tracks.  The native
integer capped weighted RMS and its native objective are also recorded at every
common location for an apples-to-apples baseline.

Hard training mean SSE selected joint basin 3; soft marginalized training
evidence selected joint basin 1.  Their conditional evaluation RMS values are
descriptive only: historical candidate discovery consulted those rows.

Shared source-rate correction is explicitly insufficient.  Under the saved
production identities no selected source recurs across scans (maximum one scan
per source), leaving no cross-scan repeated-source support for a shared rate;
such a correction could absorb position error.

Reproduce with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/sixteen_soft_orbit.py \
  --cache reports/2026_09_23_sixteen_scan_comparison/joint/cache \
  --locations reports/2026_09_23_sixteen_scan_comparison/common_finalists.json \
  --output /tmp/sixteen-soft-replay
```

Use a fresh output directory; the tool refuses to overwrite a completed run.
