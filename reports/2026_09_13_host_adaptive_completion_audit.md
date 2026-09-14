# Adaptive deployment audit

## Current status after the 21:20 UTC production slot

The earlier blocked audit below is historical. The user subsequently approved
continuation with the requested seven-minute qualification extension. All four
corrected shadow/adaptive RX0/RX1 canaries passed, and production acquisition,
API and analysis now select sealed release
`52313e7fc0b9f9f978fb0f613d25c1d152fce238`. Acquisition/API services and the
analysis timer are enabled for reboot.

The first scheduled operation succeeded as `scan-hop-8a7616c1f7b47f4a` on RX1
of the required radio at native 10 MS/s. Its 300.0546165 s source span, 95.2226%
duty, restoration and stored IQ passed qualification. All 2,381 decisions were
healthy, with no fallback. Independent replay matched every policy choice;
maximum revisit was 1.0360626 s and applied feedback age 0.2703225 s.

A fresh full background analysis cycle took 436.306686 s, or 511.306686 s with
the timer interval and accuracy. Both actual adaptive canaries have complete
native analysis and three plots. First-production analysis completed all 2,381
visits, and Chromium decoded all three production plots without page errors.
The production background cycle completed in 412.064 s. The 21:30 UTC operation
was admitted with the exact approved radio, native/decision rates and interval.
It subsequently completed as `scan-hop-8579105ea44ad910`, qualified at 95.2555%
duty. The older fixed capture was also selected successfully in the production
browser. All deployment gates are complete; normal ten-minute operation remains
active. The historical audit below is retained as evidence, not current status.
The V2 Adaptive Scan API already publishes the native recording with correct
receiver/rates, while V4 Persistent Hop history remains available.

Final qualification charges are 2,179.136778 s against the approved 2,220 s cap.
All historical charges/failures remain intact. Normal ten-minute production has
separate authorization. Tracking truthfully withholds timed TLE projection when
UTC is unqualified. See `2026_09_13_host_adaptive_deployment.md` for evidence.

## Historical audit, 20:32 UTC

The objective remains incomplete. This audit does not authorize additional RF.
The previous goal turn made progress: it corrected startup, terminal feedback and
qualification deadlines, staged the corrected runtime, and verified real native
analysis and browser products. The additional RF allowance request has no reply.

| Requirement | Authoritative evidence | Status / remaining work |
| --- | --- | --- |
| Only radio `104000bac4950008230026001b440a003a` | Live attempt receipt names this serial and `.17`; canary admission rejects another configured serial | Implemented and observed on the partial attempt; verify each successful canary and scheduled scan |
| Native 10 MS/s, one physical RX selected once per durable scan | V4 schedule contracts, component tests, partial receipt RX0/native rate | Implemented; full RX0 and RX1 canaries still required |
| 2.5 MS/s host decisions, six screens and one confirmation | Staged detector manifest, source verification, saved replay, real partial receipt | Implemented; corrected terminal drain requires live requalification |
| Unchanged adaptive policy, fresh feedback and bounded revisit | Independent replay matched all 2,372 partial-run choices; max applied age 0.263521 s, max revisit 1.0287823 s | Partial-run evidence passes; repeat on complete shadow/adaptive runs for both RXs |
| Full 300 s capture, continuity and restoration, at least 95% duty | Partial run 298.8281694 s, 95.2119%, restored, terminal cancelled | **Failed duration gate**; corrected harness must produce a full qualified recording |
| Native analysis and three plots | All 2,371 real retained visits analyzed; V2 API `figures_ready`; Chromium decoded three PNGs without page errors | Verified for partial capture; verify first complete scheduled capture |
| Ten-minute sustainable publication cadence | Saved full-capture analysis plus plots took 410 s; native worker bound four; backfill now permits a complete pass before derived products | Full production cycle, including refinement/tracking and timer delay, still needs measurement; isolated analysis throughput alone is insufficient |
| Adaptive Scan UI, correct RX/rate labels, old records preserved | Staged UI browser evidence for both synthetic RXs and real RX0; old contract tests; production API selector remains old | Implemented/staged; production browser verification remains after cutover |
| Ten-minute continuous adaptive production | Existing fixed scanner is active; 20:20 fixed scan succeeded; 20:30 operation leased at audit time | **Not deployed**; acquisition/API selectors and analysis override remain baseline |
| Rollback readiness | Private baseline backup at `/root/leo-host-adaptive-cutover-20260913`; fixed capture resumed and succeeded after failed qualification | Prepared; keep baseline selectors/environment until live gates pass |
| Bounded RF qualification | Live ledger still has 1,800 s cap, 593.374663 s charged, 1,206.625337 s remaining | A fresh RX0 plus three remaining canaries and first scheduled verification require 1,500 s before overhead; requested extra 420 s is pending |

Latest corrected sealed runtime:
`/opt/leo-tracker/releases/52313e7fc0b9f9f978fb0f613d25c1d152fce238`.
Its publication marker exists, but production selectors still name acquisition
`1212242843055e7e4079143ab1940532e8ac76fd` and API
`7f82cf42571c6d5300088acc44251885e464fa9c`. Do not infer deployed state from a
successful staging marker, tests, or the local browser preview.

No new qualification capture was started during this audit. Keep the failed
attempt and its historical charge intact. Approval of the pending allowance is
required before resuming the proposed qualification sequence; automatic goal
continuation is not an answer to that request.
