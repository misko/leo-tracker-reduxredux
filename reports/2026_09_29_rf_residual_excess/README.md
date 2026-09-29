# Cross-band candidate residual transfer

**Do not promote this correction to geographic fitting.** Separating a candidate's
donor residual slope from its receiver/RF baseline expands matched coverage from
two exact-RF cases to 81 cases, but does not improve paired held residuals reliably.
There is no new geographic error estimate or demonstrated sub-km improvement.

| Target panel | Matched / eligible cases | Zero-slope median Hz | RF-only median Hz | Candidate median Hz | Shuffled median Hz | Candidate wins vs RF | Median paired gain vs RF, Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS8 late 8 | 2/429 | 120.96 | 123.63 | 42.88 | 130.99 | 2/2 | +80.76 |
| DS9 middle 8 | 31/446 | 137.94 | 137.87 | 175.34 | 156.27 | 12/31 | -3.62 |
| DS9 late 8 | 48/429 | 157.82 | 157.59 | 127.68 | 167.39 | 24/48 | -0.38 |
| All matched | 81/3,983 | 140.27 | 141.33 | 140.25 | 160.09 | 38/81 | -0.95 |

Errors are medians across cases of each case's median absolute held residual.
Positive paired gain means the candidate correction reduces error. A difference
between aggregate medians is not the median paired improvement: late DS9 illustrates
why both must be reported. Candidate transfer beats zero slope in 39/81 cases and
the shuffled excess in 45/81, with median paired gains -0.68 and +12.25 Hz respectively.
Two DS8 cases are insufficient to establish dataset-wide transfer.

The other six panels have no supported transfer: DS7 early/middle/late have
447/438/461 eligible cases, DS8 early/middle 461/421, and DS9 early 451. The 3,983
eligible target cases are a previously selected subset of 4,328 tracks in 72 scans;
81 matched cases represent 2.04% of eligible cases and 1.87% of all target tracks.
No unmatched case was assigned an improved score. No single-scan location or full
four/eight-scan mixture likelihood was evaluated here.

## Method and provenance

[Protocol](PROTOCOL.md) was frozen before execution. The experiment reuses the
[exact-RF study's](../2026_09_29_donor_residual_transfer/README.md) conditional
residuals: 9,968 donor cases in 25 disjoint donor groups from 186 scans. Candidate
numbers are catalogue identities under fitted associations, not verified identities.
Each donor group must finish strictly before the target scan starts.

Within each donor group/RX/RF cell, subtract the median slope of at least two other
candidate numbers from the target candidate's median slope. Median across RF lanes,
then across at least two groups. Add this excess to an independently estimated
target-RX/exact-RF baseline, also requiring at least two prior groups and two other
candidates per group. Every arm uses the target's original training residual/time
means. Held observations do not estimate the correction.

The shuffled control rotates slopes one case within each sorted donor group/RX/RF
cell; it retains the **real RF baseline**. Of 9,967 rotated cases, 1,310 (13.14%)
retain the same candidate label. One singleton is unrotated. This is an imperfect
identity control, not a calibrated null distribution. No shuffle seed was selected.

[Source provenance](source-audit.json) preserves three installed extraction modules.
Their code scales CFO and alias spacing by canonical 11.2 GHz / actual RF, then
exports lane-specific normalized observations. Thus slopes have comparable units
across bands; this does not remove hardware bias. Exact RF values are preserved for
baseline grouping. This code audit did not replay raw waveform extraction.

## Verification and decision

Four prelaunch tests pass, covering known excess recovery, temporal/RX isolation,
held-data and input-order independence, and minimum other-candidate support.
The numerical child exits zero in 9.61 seconds, peak RSS 133,128 KiB.
[Independent audit](audit.py) reconstructs grouping, both control predictions,
all support decisions and training/held scores using separate code and verifies
frozen input/execution hashes. All 81 matched cases pass. The auditor has one
cosmetic import-order lint finding; execution sources passed lint before freezing.

No thresholds changed, no scientific child was retried, and no new RF, raw IQ,
orbit propagation, archive/provider query, position fit or production change occurred.

The result does not support a stable transferable candidate slope correction.
Keep the existing geographic baseline. A next experiment should address independent
association or observing-opportunity evidence rather than tuning this correction
against exposed location errors. [Next investigation](NEXT.md).

[Full results](result.json), [summary](summary.json), [tests](tests.log),
[execution receipt](exit.json), [resources](resources.txt),
[input seal](input-seal.json), [execution seal](seal.json),
[complete evidence inventory](evidence-sha256.json).
