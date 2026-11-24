# Detector support and ownership on four complete DS30 pairs

All four successor packets had **more passing native lanes and fewer
published owners**. DS30-0274 lost 939 installed-positive lanes and gained
1,013 distinct lanes. Its fitted error rose **0.206 → 0.934 km** even though
the median absolute CFO change on all 5,583 common positives was the
smallest of the four. DS30-0019 improved both positions while losing the
most net owners. The paired DS30-0049 crossover is the only case here that
isolates the receiver as the cause of its geographic regression.
[Frozen method](ds30-owner-support-four-protocol.md) ·
[Complete per-receiver/channel receipt](measurements/ds30-owner-support-four.json.gz) ·
[DS30-0049 crossover](ds30-0049-saved-crossover.md)

| Case | Passing native lanes installed → successor | Both passing / lost / gained | Median absolute CFO change on both passing | Published owners installed → successor, per arm | Successor owners on installed-empty lanes | Fixed-zero / fitted error change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0019 | 4,614 → 4,996 | 4,019 / 595 / 977 | 72.9 Hz | 3,372 → 2,842 | 91 | −309 / −467 m |
| DS30-0049 | 531 → 600 | 427 / 104 / 173 | 80.2 Hz | 320 → 268 | 14 | +2,646 / +2,620 m |
| DS30-0178 | 4,330 → 4,625 | 3,622 / 708 / 1,003 | 85.5 Hz | 2,996 → 2,875 | 93 | +240 / +219 m |
| DS30-0274 | 6,522 → 6,596 | 5,583 / 939 / 1,013 | 69.1 Hz | 4,418 → 4,139 | 134 | +717 / +727 m |

The lane denominator is 11,954, 1,864, 11,702 and 13,526 admitted stereo
lanes respectively. Each has a single signed session, receiver and
hardware start counter, with identical RF, channel and edge across
methods. A passing lane contributes its highest fractional-margin
passing candidate, using original candidate rank to break ties. CFO
displacement is the signed successor measurement minus the installed
measurement before alias lifting. The table takes its absolute median
on the exact both-passing denominator. All four successor selectors
chose `unfiltered` and made zero refinement calls. The owner counts
and comparison totals in the table are equal across the two arms.

## Where the support changed

- **DS30-0019** lost 355 of 595 original positive lanes on channels
  5–8. RX1/CH5 and RX1/CH8 lost 74 and 66. Of the 91 successor
  owners on installed-empty lanes, 52 are on RX2. Both geographic
  errors improved while terminal RF RMS rose from about 144 to 175 Hz.
- **DS30-0049** lost 74 of 104 original positive lanes on RX2. The
  verified installed row list gives **249 exact retained, 71 lost and
  19 gained owners**, with no NORAD or role change on retained IDs.
  RX2/CH6–8 fell from 40 to 13 owners, with 29 losses and two additions.
  The exact retained-owner median absolute CFO change is **79.6 Hz**
  across 249 matched owner IDs. Both arms have the same join.
- **DS30-0178** lost 412 of 708 original positives on channels 5–8.
  The corresponding gain was 414. CH5 alone lost 87 lanes on RX1 and
  77 on RX2. The 93 successor owners on installed-empty lanes divide
  as 63 on RX1 and 30 on RX2.
- **DS30-0274** lost **651 of 939** native positives on channels 1–4.
  That band fell **3,789 → 3,636** passes while channels 5–8 rose
  **2,733 → 2,960**. RX1/CH3, RX1/CH1 and RX2/CH3 contributed 107,
  99 and 90 losses. Both receivers gained 37 passing lanes overall.
  The successor took **65.543 s** against **133.811 s** installed
  through common verification on separate leases. Its fixed-zero
  error rose **0.172 → 0.889 km**. Terminal RF RMS rose about 30 Hz
  in each arm.

## What the published owner evidence identifies

The successor witnesses expose ordered owner rows, and the original
DS30-0049 crossover supplies installed rows independently verified
against the same raw terminal and owner digest. The installed
publications on DS30-0019, DS30-0178 and DS30-0274 expose owner totals
and hashes. Their exact per-lane membership remains unavailable from
these receipts.

Each unknown installed owner must belong to the installed passing
universe. If that universe has size `N`, an observed group contains
`K` eligible IDs and the installed publication has `n` owners, the
number of owned IDs in that group can range from
`max(0, n - N + K)` through `min(n, K)`. The receipt uses this for
each stream's possible matched, lost and gained owner counts. Bounds
on individual streams are often wide and cannot be summed as a
simultaneous result. At complete-recording scope, at least
**621, 214 and 413** installed owners were lost on DS30-0019,
DS30-0178 and DS30-0274 respectively. The counts on installed-empty
lanes in the table are exact minimum additions.

Among successor owners with a passing installed lane, the median
absolute CFO changes are 63.7 Hz on DS30-0019 (2,751 possible
retained IDs), 76.0 Hz on DS30-0178 (2,782) and 61.7 Hz on DS30-0274
(4,005). These are eligible pools. The true retained medians could
span 22–125, 23–148 and 18–127 Hz respectively using the observed owner
totals and exact passing lanes alone. They provide no reliable
cross-case ranking of retained-owner CFO stability. The independently
scored positions and terminal RF fits are in the machine receipt.

## One test for the long-primary experiment

On a prospective long recording, match paid receiver CPU, issued
opportunities and solver across the long-primary and sparse8 arms.
Use the **lowest installed-positive recall across occupied
receiver/channel streams** as the detector outcome. Require an
improvement in that outcome with neither calibrated geographic
error worsening versus sparse8. Either failure falsifies the proposed
improvement. The detector rule uses no surveyed position and gives
all occupied streams the same definition. The independent geographic
check follows the predecessor's original search region and is scored
after sealing. Greater overall yield and late-stage RF fit alone
would not pass this test.

The auditor reopens the frozen pair and attempt digests, independently
checks the exported campaign rows against each raw terminal and
published inventory, rederives observable owner digests and joins the
separately pinned reference audit. It opens no waveform or TLE body
and runs no solver or detector. The receipt carries every exact
stream count, CFO join and membership interval for both arms. Three
focused tests passed.
[Auditor](ds30_owner_support_four.py) ·
[Tests](../../../tests/pipeline_eval/test_ds30_owner_support_four.py)
