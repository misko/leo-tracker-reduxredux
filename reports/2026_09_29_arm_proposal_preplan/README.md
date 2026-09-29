# Proposal geometry preplan

Physical-ARM follow-up: all eight component tests passed. The four-dwell run
preserved every candidate output and measured 1.692925 seconds/dwell, versus
Wave3's two-run mean of 1.709724. Proposal folding/conversion fell to 195.990 ms
from about 215 ms. This isolated result is one timing run; the combined exact
proposal variant is measured separately in the fourth-wave report.

This isolated Wave 3 variant hoists proposal geometry that is invariant for a
workspace and sample rate.  It precomputes every power-of-two resampling source
index and float fraction, the 16 frame offsets, each lag's valid length, and
each original cell's support count.  Window folding no longer updates a support
array, and resampling performs no integer division or remainder operation.

The original float interpolation expression and per-cell division by the
integer support count are retained.  Reciprocal multiplication was deliberately
not introduced because it need not be bitwise equal to division.  Proposal
features, ranking, candidate geometry, and the FP64 final GLRT are unchanged.

`python3 build.py` creates host, sanitizer, and Cortex-A9 cross-builds with
exact commands and hashes in their receipts.  Host and sanitizer execute the
seven inherited Wave 3 tests plus `test_preplan`, which checks resampling
geometry and bitwise fold/resample parity for both receivers, lags 1/3/5, all
four rates, and deterministic full-range CI16 input.  ARM is cross-built only.

The expected opportunity is lower proposal fold/conversion CPU time from
removing repeated support updates and resampling division/modulo.  No saving is
claimed until target timing confirms it.

The 704-dwell host qualification produced exactly the same 123,904 candidate
objects as sealed Wave 3: zero changed candidates and zero changed windows.  Its
independent standard audit therefore also matches Wave 3 at 19,226 recovered
positive hits out of 19,581, with 21,505 unmatched positive hits.  Host timing
from this qualification is not used as a speed claim; the intended decision is
the serialized Cortex-A9 measurement.
