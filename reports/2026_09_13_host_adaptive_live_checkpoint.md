# Native host-adaptive deployment checkpoint

Release `f33bee7f892129496360508f477c7a343e6b1189` is staged and sealed,
but has not been selected for acquisition or API production.

The installed Python 3.14 runtime replayed saved native 10 MS/s session
`scan-hop-a942a0bce610f262`: all 2,387 visits completed with four workers,
120 ms probe stride and one BLAS thread per worker. Analysis took 407.435 s;
analysis plus three overview PNGs took 410.000 s, below the 600 s cadence.
Policy and counters were synthetic; IQ was from the saved physical RX0 capture.
This establishes analysis cost, not live adaptive scheduling or sensitivity.
Evidence: `/var/tmp/leo-host-native-cadence-20260913-v2/qualification.json`.

The first shadow RX0 canary failed before radio acquisition with `RadioBusyError`.
The shared global authority lease was held by PID 666359, a separate radio20
frequency-revisit qualification process. No lock was bypassed and that process
was not changed. The failed call is conservatively charged 8.002823 s, leaving
1,554.665735 s of the original RF allowance. No adaptive RF was collected by
this attempt. Evidence and the failed-attempt ledger remain at:

- `/srv/bulk/leo/qualification/host-adaptive-20260913/shadow-rx0/canary.json`
- `/var/tmp/leo-host-adaptive-rf-ledger-20260913.json`

Acquisition was stopped between scans at 19:58:43 UTC, then restarted at
20:04:23 UTC on its unchanged fixed profile. The 20:00 slot remained pending
because the same shared lease also prevented production capture; systemd retries.
The last completed slot was 19:50, session `scan-hop-5998a655aaddb867`,
2,386 visits and 95.4249% duty. Starting the service is not proof of resumed RF.

Next: verify lease availability and resumed production, review the failed
pre-acquisition attempt explicitly in the ledger, then run the four reserved
300 s qualification scans. Restore their full 1,200 s reservation plus the
300 s first scheduled verification when updating ledger bookkeeping: the failed
pre-acquisition attempt did not consume a successful canary. Stop on any live
gate failure. Only select the staged adaptive release after qualification passes.
Only radio `104000bac4950008230026001b440a003a` is authorized for this task.

The new UI reader places native host-adaptive captures under Adaptive Scan,
showing native 10 MS/s, physical RX and 2.5 MS/s decision processing. Historical
fixed-order captures remain under Persistent Hop + Scan. This UI is staged,
not yet the production reader.

## Follow-up at 20:12 UTC

The delayed 20:00 fixed scan completed with 2,387 visits and 95.4538% duty
(`scan-hop-036f6e40a71ba826`). The service was paused after its success.
The first lease failure was explicitly reviewed as pre-acquisition; its charge
was preserved and the full successful-canary reservation restored.

Shadow RX0 attempt 2 reached host startup but failed before opening the capture:
`profile frequencies and CRC must be non-zero`. PPU validated the complete wire
request before `prepare_plan` populated hardware fastlock CRCs. PPU commit
`37fa76e161c1dd9fe2ee6b171c1f0a80ac2578e2` validates policy/configuration first,
then validates the complete wire request after preparation. Regression coverage
now starts with zero CRCs for both RXs and also rejects missing prepared CRCs.
The focused PPU suite passed 666 tests. Corrected Leo release
`da7edddafe2c06dbf281c1dbd4e7f6f54f1c9130` is being staged.

The failed attempt remains charged 11.871408 s in the ledger; no receipt or IQ
was published. Fixed acquisition was restarted, but its 20:10 slot exhausted
retries on a separate shared-lease collision. The service remains scheduled for
the next slot. No other task's process or radio was changed.

An independent Python saved-trace verifier now checks every healthy HOPS choice
against source-ordered applied host evidence, weights, cooldowns and revisit
gaps. Its component tests plus canary gate tests passed 21 cases, including both
RXs, changing activity, and deliberate trace corruption. It does not interpret
feedback transport acceptance alone as proof of policy application.

The native analysis measurement also exposed a 300 s per-pass backfill budget,
shorter than the measured 407 s metrics computation. Commit `1bf2bf6f` moves
adaptive analysis ahead of derived products and permits 580 s per pass, retaining
four native workers and 120 ms probe stride. All 15 backfill tests passed.
Release `2824e625b5f9f732696fab941c813c78cc353d57` contains this change plus the
CRC fix and passed immutable staging, web asset generation and installed-runtime
validation. It remains unselected pending live qualification. Full maintenance
cycle timing must still be measured; the 410 s replay measured native analysis
and overview only, not additional refinement/tracking jobs.

## Real RX0 shadow attempt and corrections

Attempt 3 on release `da7eddda` published partial session
`scan-hop-1d536e8d58c6d191`, manifest
`sha256:e70544b30d6c936c61858d3b99b413b165956aa433069d96d0a072d3d9970a33`.
It retained 2,371 visits across 298.8281694 s with 95.2119% duty, no policy
fallback and verified restoration. It is **not qualified**: the harness's
310 s deadline included startup and cancelled about 1.2 s before completion.
Its entire 336.168990 s call plus verification remains charged. The ledger now
has 593.374663 s charged and 1,206.625337 s remaining. A fresh RX0 canary plus
the remaining three canaries and first scheduled verification need 1,500 s of
RF before overhead. An additional allowance of at most 420 s was requested;
no further qualification RF is authorized unless that request is approved.

All 2,372 observed policy choices passed the independent replay. Maximum actual
revisit was 1.0287823 s and maximum applied source age was 0.263521 s. The one
degraded result was the final visit, explicitly `source_ended`: detector work
took 170.907 ms but feedback age reached 1,321.141 ms across restoration. None
of the 2,370 accepted records was degraded. These observations do not turn the
cancelled scan into a successful live gate.

PPU `ac7dae8796099ad63dad2bc9700bf52638c8450a` provides an owner-thread terminal
drain before restoration, explicitly marking results unapplied once terminal
status proves the source ended. Leo drains bounded outstanding computation there,
then processes any final retained IQ and closes its worker normally. Tests cover
callback failure cleanup, slow restoration, and preservation of workspace for
terminal IQ. The canary now bounds the capture call to 335 s, disarms that timer
before verification, and charges the capture call rather than offline verification
on future attempts. Historical charges are unchanged. PPU passed 682 tests;
Leo passed 59 focused tests, mypy and Ruff. Corrected immutable release
`52313e7fc0b9f9f978fb0f613d25c1d152fce238` passed staging and remains unselected.

The real partial capture completed native 10 MS/s analysis for all 2,371 visits,
publishing metrics and all three overview artifacts. Binding:
`sha256:307f0cc44d494fe7281c1772dd4e30786e62fff242dd02ab4ce5f4699d7f2919`;
metrics: `sha256:5b2fde3a3bfe1c340c0bcab359ed7f665a9e883bf1189cc55fba842ebfe1532f`.
Evidence: `/var/tmp/leo-host-shadow-rx0-analysis-20260913.log`. A local preview
uses the staged release and real read-only capture/products; unrelated app data
uses fixtures. This is not production publication or full qualification.
Chromium decoded the real three PNGs at 2480×1040, 2480×1152 and 2480×1840
with no page errors. Evidence: `/var/tmp/leo-host-live-browser-ready.json` and
`/var/tmp/leo-host-live-browser-ready.png`. The first browser check incorrectly
waited for an offscreen lazy image before scrolling; scrolling its visible figure
container allowed normal image loading. No UI change was required.

Fixed production resumed and completed the 20:20 slot as
`scan-hop-da9e419b1dd0a21e`, 2,387 visits, 95.4405% duty. The 10-minute schedule
and exact radio003a binding remain unchanged.

## Resumed at 20:41 UTC

The user replied “please continue” after the explicit request for at most seven
additional minutes. The allowance is now 2,220 s; historical charges remain
593.374663 s, leaving 1,626.625337 s. Attempt 3 is reviewed as a failed partial
capture with tested/staged deadline and terminal-drain fixes; it is not relabeled
as passed. Reserve 1,500 s for the four canaries and first scheduled verification.

Private acquisition and analysis cutover candidates were generated beneath the
existing root-only backup directory and validated with the staged settings parser.
The baseline acquisition environment still matches its backup. No selectors or
production environment were changed. The 20:40 fixed scan is allowed to finish
before pausing scheduled starts for the bounded canaries.
