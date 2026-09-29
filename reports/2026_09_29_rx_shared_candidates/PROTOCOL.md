# Shared candidate support: frozen descriptive census

Use all 913 published training-selected RX0/RX1 pairs over the same 72 scans.
Use only the nine nonoverlapping eight-scan panels for each scan's original
q020 training-selected position and conditional signal candidate weights.
No new fit, propagation, candidate search, calibration or geographic selection.

For each bank-eligible pair, require both candidate lists to share the same
manifest, pinned baseline snapshot and catalogue size. IDs are catalogue rows,
not NORAD IDs. Validate unique integer IDs, range, array sizes and normalized
finite nonnegative weights. Preserve pairs missing either eligible bank; never
silently exclude an empty intersection.

Report raw candidate intersection, each RX's conditional signal mass within
that intersection, sum of products of independent conditional weights on equal
rows, and whether conditional MAP rows match. Break exact MAP ties by smallest
row index. The product sum is a model-agreement diagnostic, not calibrated
identity confidence. Signal responsibilities are reported separately. Zero
stored weight can reflect underflow and is distinct from absent bank support.
The existing training-fitted location influences these candidate weights.

Control: within each scan/channel/exact RF, sort selected pairs by (RX0,RX1)
and cyclically rotate the RX1 partners once. Require at least two selected pairs;
otherwise report unavailable. A shuffled partner is not verified to be a different
satellite. Compare actual versus control only when both pairs have eligible banks.
No held observations or reference coordinate decide support or control membership.

Freeze code, six tests, all input paths and hashes before execution. One child,
90-second timeout, 4 GiB address space, BLAS1/nice19 and ≥5 GiB available RAM.
Read candidate-ID arrays only from cached NPZs; do not load orbital arrays,
archive data, raw IQ or provider inputs. Retain every selected pair and all
missing/control reasons. This stage does not score held prediction or report
new geographic accuracy. A later uncertain shared-identity model requires its
own normalized likelihood, controls, tests and frozen scoring protocol.
