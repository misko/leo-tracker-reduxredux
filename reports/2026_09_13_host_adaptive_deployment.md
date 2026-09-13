# Native 10 MS/s adaptive deployment

Production acquisition, API and analysis select sealed release
`52313e7fc0b9f9f978fb0f613d25c1d152fce238`. Acquisition and API services and
the analysis timer are enabled for reboot. The acquisition environment selects
`adaptive-single-rx-random-10m-300s-v1`, with 600-second UTC slots and only radio
`104000bac4950008230026001b440a003a` (`radio_pluto_003a`). One physical receiver
is selected once per durable scan. Native IQ remains 10 MS/s; host decisions use
the manifest-bound, factor-four 2.5 MS/s stream, six screens and at most one blind
confirmation. On-radio GLRT is disabled.

## Qualification

All four corrected canaries completed, restored receiver state, passed stored-IQ
verification, and matched the independent adaptive policy model. No degraded
host results or fallback choices occurred.

| Mode / RX | Session | Source span (s) | Valid duty | Maximum revisit (s) |
| --- | --- | ---: | ---: | ---: |
| Shadow RX0 | `scan-hop-1d536e8d58c6d191` | 300.0797219 | 95.2546% | 1.0274656 |
| Shadow RX1 | `scan-hop-1d0a67972b4d90a9` | 300.1065474 | 95.2461% | 1.0213422 |
| Adaptive RX0 | `scan-hop-89ff5771b72d879c` | 300.1034083 | 95.2071% | 2.7801128 |
| Adaptive RX1 | `scan-hop-106c90486d2e961d` | 300.0918175 | 95.2508% | 1.0237280 |

Adaptive RX0 exercised 2,296 weighted choices. RX1 had no active targets and
correctly continued uniform coverage after warmup. These observations establish
policy execution, not satellite identity or counterfactual detector sensitivity.
Detailed reports are beneath
`/srv/bulk/leo/qualification/host-adaptive-20260913/`.

The original partial attempt remains failed: its old harness deadline cancelled
at 298.8281694 s, and restoration delayed terminal feedback. The corrected
capture deadline and pre-restoration feedback drain were tested and qualified;
the historical charge was not reduced. The separately approved seven-minute
extension increased the qualification cap to 2,220 s. Final conservative charges
are 2,179.136778 s, with 40.863222 s unused; no further qualification RF is planned.
See `2026_09_13_host_adaptive_rf_ledger.json` for every attempt.

## First scheduled production capture

The 21:20 UTC operation succeeded as `scan-hop-8a7616c1f7b47f4a`:

- RX1, native 10 MS/s, 300.0546165 s source span, 2,381 retained visits.
- Qualified, completed and restored; 95.2226% valid capture duty.
- 2,381 healthy decisions: 2,379 accepted and two terminal source-ended results.
- No fallback, rejected or unsubmitted results; maximum host result age 165.557 ms.
- Independent replay matched all 2,381 choices; maximum applied age 0.2703225 s
  and maximum revisit 1.0360626 s.

Evidence: `/var/tmp/leo-first-scheduled-host-adaptive-20260913.json` and
`/var/tmp/leo-first-scheduled-host-adaptive-gates.json`. The persisted V4 intent
binds the exact radio, RX1, both sample rates, adaptive policy and 600-second
interval. Slot-to-publication elapsed time was 320.161663 s and is conservatively
charged in full to qualification.

## Analysis and web verification

Native analysis completed for both actual adaptive canaries, including all
retained visits and three plots. A fresh full background sequence on the
qualified shadow RX0 recording took 436.306686 s including refinement and
tracking evaluation. Adding the configured 60-second timer interval and
15-second timer accuracy gives 511.306686 s, below the 600-second cadence.
Evidence: `/var/tmp/leo-host-full-backfill-20260913.json`.

The production V2 Adaptive Scan API publishes the first native recording with
correct physical receiver and decision configuration. The V4 Persistent Hop
history remains available. Production HTML, JavaScript and CSS return HTTP 200.
First-production analysis completed all 2,381 visits and published three plots
at 21:33:48 UTC. Chromium decoded coverage (2480×1040), GLRT response
(2480×1152) and CFO candidates (2480×1840) at 21:34:18 UTC, with no page errors.
Evidence: `/var/tmp/leo-host-production-browser-20260913.json` and `.png`.
The production background cycle ran from 21:27:13 for 412.064 s (6 min 52 s),
including tracking evaluation, and exited successfully. Publication occurred
about 509 s after capture finalization, before the next recording was due.

The next 21:30 UTC operation was admitted on schedule with the same native and
decision rates, exact approved radio and 600-second interval. It independently
selected RX1; random selection does not require alternating receivers.
It subsequently succeeded as `scan-hop-8579105ea44ad910`, with 2,382 retained
visits and 95.2555% duty, qualified and completed. Acquisition, API and analysis
timer remain active.

The existing fixed capture `scan-hop-58347bfce4927c0a` was selected successfully
in the production browser with its 10 MS/s label and complete-analysis status.
Evidence: `/var/tmp/leo-host-production-fixed-browser.json`. Earlier browser
waits expired during concurrent loading; the final check passed, and subsequent
API checks returned HTTP 200 in 5.23 s for legacy analyses and 0.93 s for the fixed
history page. No history migration or relabeling was required.

UTC timing is unqualified on these captures; tracking truthfully declines timed
TLE projection. This is not evidence of a native sample-rate analysis failure.
Automatic analysis uses one 20 ms native-rate probe per 120 ms dwell; the complete
recorded IQ remains retained. The reported duty is within each acquisition;
300-second acquisitions start every ten minutes.

## Recovery

Baseline environment and analysis drop-in are retained privately under
`/root/leo-host-adaptive-cutover-20260913`. The prepared rollback helper is
`/var/tmp/leo-rollback-host-adaptive.sh`. Immutable baseline releases remain
available. No firmware change, QNAP mutation or corpus migration was performed.
