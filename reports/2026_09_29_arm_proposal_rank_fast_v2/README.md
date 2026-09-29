# Proposal linear top-four rank fast v2

The first linear top-four prototype mapped every local maximum to the original
proposal grid during each of four passes.  On Cortex-A9 that was slower than
the sorted baseline.  This isolated v2 adds one exact rejection before mapping:
once a pass has a best candidate, a later candidate with an equal or lower
score cannot replace it because bins are visited in ascending order and the
required tie break favors the earlier bin.

The sorted `qsort` implementation remains in the source as the test oracle.
The component test compares v2 with that oracle at every supported rate for
flat input, equal-score ties, wraparound peaks, and circular separation.  No
proposal score, candidate rule, or final GLRT arithmetic changes.

`python3 build.py` creates host, sanitizer, and ARM cross-builds with exact
commands and hashes in each receipt.  ARM execution remains delegated to the
serialized target runner.  No benefit is claimed until target timing.

The 704-dwell host qualification matched rank-fast v1 exactly across all
123,904 candidate objects, with zero changed candidates and windows.  The
independent standard audit is consequently unchanged at 19,226 recovered hits
out of 19,581 and 21,505 unmatched positive hits.  Host timing is recorded for
diagnostics only and is not an ARM speed claim.
