# Wave 7 alternate-window proposal tracking

This approximate prototype starts from sealed Wave 6 combined.  It computes
full lag proposals for even windows 0, 2, 4, 6, 8, and 10 for both receivers.
For each odd window it translates both adjacent proposal banks through absolute
sample coordinates using the exact `rate/750` period and rounded proposal grid.
If at least two one-to-one neighbor peaks agree within four circular cells, it
uses their consensus-first union (up to four centers).  Otherwise it computes a
fresh full proposal on current-window IQ.  Every window still runs the full
current-IQ coarse, fine, conditioned, and final FP64 GLRT stages.

This differs from the rejected endpoint interpolation experiment, which sent
first/last candidates and CFO directly into restricted middle-window GLRT and
recovered only 653/843 hits.  Here interpolation affects only the pre-coarse
epoch search regions.  Fallback depends solely on neighbor proposal agreement,
never final positives or ground truth.  Proposal stability is a measured
hypothesis; CFO stability does not establish it.

Host/sanitizer component suites pass, including all-rate fractional-period
translation, wraparound, agreement, disagreement, full-scale input, dwell
views, shared folding, exact radix ranking, and existing search tests.  ARM
artifacts are cross-built only.

On Host32, 148/320 odd receiver-windows reused translated proposals and 172
fell back.  Full proposal work was 556/704 windows (79.0%).  The standard audit
recovered 921/948 hits (97.15%).

On Host704, 3,437/7,040 odd receiver-windows reused translated proposals and
3,603 fell back.  Including 8,448 even anchors, full proposal work was
12,051/15,488 windows (77.81%), a 22.19% reduction.  The audit recovered
19,208/19,581 standard hits (98.10%), nine fewer than the current 19,217-hit
Wave 6 result.  It emitted 16,581 unmatched positive hypotheses; those are not
confirmations.  It changed 9,815 candidate objects in 2,296 windows versus the
Wave 6 combined control.  This does not meet the preserve-current-hits goal and
should remain experimental.

`host704-hit-identities.json` applies the frozen one-to-one timing/CFO matcher
and records baseline candidate identities.  Relative to Wave 6 combined, the
two-match policy loses 20 previously recovered identities and gains 11
different identities, for the observed net loss of nine.  Gains are matcher
recovery differences, not evidence that new hypotheses are physically true.

The host mean measured outer total was 72.8067 ms/dwell, but host timing does
not predict Cortex-A9 savings.  The work counters bound the possible proposal
gain to about 22%; hardware timing is intentionally not run here.

Two versioned agreement thresholds define the quality/work frontier.  `min1`
reuses any odd window with one matched neighbor seed: Host704 runs 9,652 full
proposals and recovers 19,205/19,581 hits.  `min4` requires all four seeds to
agree: it reuses only 214 odd receiver-windows, runs 15,274/15,488 full
proposals (98.62% work), and recovers 19,214/19,581.  Thus strict agreement
closes six of the nine-hit gap but provides only a 1.38% proposal-work saving;
permissive reuse increases the loss.  Neither preserves all current hits.

Rebuild with `python3 build.py`.  The ARM runner is:

```
builds/arm/fused_wave7_proposal_tracking_arm RATE EXACT CONTROL INPUT_CI16
```
