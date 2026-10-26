# Exact eight-window replay and fixed-candidate refinement

The eight requests in ../influence/window_requests.json are immutable. They
come from four complete accepted owners, with two fixed chronological
quantiles per owner. No owner/window/rank replacement, trimming, new graph,
satellite search, position fit or GPS use. The task is measurement parity
and a bounded same-score numerical refinement, not localization evaluation.

Use the original recorded authority.json and the exact persisted policy for
each case. The historical runtime must match both code and environment
digests before and after the worker. Verify all frozen sources, requests,
tracking exports, refiner and authority hashes before any payload read.

For each request in frozen order, construct the public FastSegmentSource
from its explicit segment reference, bounded to the selected local sequence.
Exhaust its iterator before detector use: that verifies every window/hash in
the containing compressed/decompressed chunk. Check the returned IQ hash,
native acquisition support, target, receiver identities and sample rate
against the metadata-frozen request. No private storage methods or fabricated
storage paths. Source input, segment manifest and declared index hashes remain
mandatory. These requests have zero RF-center calibration offset; reject any
contradiction rather than changing the refiner's coordinate convention.

Invoke historical analyze_window with production_glrt and the original
policy on BOTH native receivers, once per physical request: at most8 paired
detector calls. Preserve full replay result, including acquired CFO and its
fractional refinement residual, which the old tracking export omitted.
Compare EVERY exported candidate on BOTH receivers with the original tracking
window, not just the selected winner. Candidate count/order, rank, integer
epoch and original gate must agree exactly; fractional epoch tolerance1e-9
samples, tracking CFO1e-6Hz, exact/control/margin1e-10. No mismatch is waived.

Only after whole-window candidate parity passes, find the REQUESTED receiver's
ORIGINAL winning rank. Do not rerank after refinement. Pass the replayed
acquired CFO, original integer/fractional epoch, fractional residual and scores
to unchanged measurement/refiner.py::refine. Preserve original gate and alias
coordinates. The refiner itself must replay the original512-bin score before
optimizing only inside the original winning residual-frequency cell. Keep all
its numerical frequency/margin/boundary/reference flags; an unqualified result
is diagnostic, never silently replaced by another candidate or widened cell.

Save original/replayed acquired and final CFO, continuous candidate CFO delta,
both scores/margins, parity/closure flags and compact exact/control correlations
for independent saved-node audit. These are derived correlation arrays, not IQ.
There is no real CFO truth, so report correction magnitude rather than field
error reduction. Paired owner summaries require both fixed quantiles complete;
four case×quantile target/control comparisons remain separate, not independent
confirmations or evidence of a whole-owner bias shape.

One worker and one BLAS thread. Cumulative numerical cap180seconds includes
preparation/tests and a conservative2second earlier source-import allowance.
Use one immutable run, at most8 paired detector calls, no retries/cap growth.
An exception stops further requests; preserve the current failed stage and all
remaining requests as not_attempted. Timeout likewise stops globally. Keep
parity-pass/raw checkpoints in the final structured output even if subsequent
refinement fails. All8 slots always appear.

The service-user worker reads only and prints one JSON object on stdout; the
coordinator redirects it into a user-owned result file. Do not write science
files as the service account or mutate original inputs. Test pure parity,
full iterator exhaustion, count limits/failure-stop accounting and fixed-rank
selection before source freeze. Preparation loads metadata and original runtime
identity only: no IQ or detector. B exact preflight plus the coordinator's
authorization are required before execution. The coordinator has authorized
the frozen run after synthetic evidence and B PASS; no earlier call is allowed.
