# Receiver/RF baseline plus cross-band candidate residual excess

Use the unchanged conditional residual cases from the completed exact-RX/RF
study. No new waveform, state prediction, position/timing fit or track selection.
Exported CFO and alias spacing are normalized to 11.2GHz by actual RF. Tracklets
are lane-specific; rf_hz is their first point's actual RF. Preserve a source
audit of the installed extraction chain and the repository exporter.

Normalization makes slopes dimensionally comparable across RF; it does not
remove hardware or propagation biases. Test the following new statistical
hypothesis, without changing the previous exact-match result:

Within each donor group/RX/exact-RF lane, take the median slope for each strong
candidate number. A candidate excess is its median minus the median of other
candidate medians, requiring at least two other distinct numbers. For a candidate
observed in several RF lanes, median its excesses within the donor group. Then
median across at least two independent available donor groups at the target RX.
Only groups ending strictly before the target scan start are available.

Estimate the target RX/exact-RF baseline independently from at least two available
groups, using median per-candidate slopes excluding the target candidate and at
least two other distinct numbers per group. Those groups may differ from the
candidate-excess groups. Add the median candidate excess to this baseline.

Controls on the same cases: zero slope; RX/RF baseline alone; and a shuffled
excess formed by cyclically rotating slope values by one case within each
donor group/RX/RF cell, sorted by number/session/track. Keep the unshuffled target
RF baseline for that shuffled-excess arm. The shuffle preserves cell membership
and slope distributions but can leave candidate labels unchanged when repeated;
report that fraction rather than claiming a perfect null. Do not select a seed.

Require both real and shuffled predictors to have the frozen support. Use the
same target training residual/time means for every arm. Score per-case median
absolute held residual; report all target denominators and failures. Positive
paired gain means lower error. This remains a conditional diagnostic, not a
normalized held mixture likelihood, identity probability or geographic result.
No threshold tuning, clipping, retries or promotion solely from these errors.

Four synthetic tests check exact excess recovery, chronological/receiver isolation,
held/order invariance and minimum control support. One source-audit preparation
and one numerical child, timeout90s, AS4GiB, BLAS1/nice19, available RAM >=5GiB.
No RF, raw IQ, propagation, archive/provider access or production changes.
