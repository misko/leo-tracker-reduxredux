# Adaptive scanner: cooldown policy and positive-only feedback

2026-09-09. **Implemented and tested offline; adaptive hopping and deployment
are not complete.** No radio was accessed and no RF, firmware flash, FPGA,
kernel or production-service change was made.

## Delivered

The pure native scheduler implements three-miss **and** two-second demotion,
immediate positive promotion, 3:1 active/quiet weighting, startup exploration,
independent lower/upper targets, nominal three-second exploration protection,
source-order observations and latched equal-scan fallback. Unknown results
break the miss streak. Integer device-counter times, not result arrival times,
anchor the cooldown. Allocation is deterministic and cannot stop acquisition
while awaiting GLRT.

All 256 activity combinations pass. The four-target case with 1, 3 and 4 active
allocates 30% to each and 10% to target 2. These are synthetic policy results,
not measured RF duty or observed satellite coverage. Exploration overrides may
alter the nominal ratio. An OS/retune deadline overrun remains measurable and
cannot be converted into a hard realtime guarantee by the policy alone.

An additive positive-only SDK entrypoint now applies an explicit threshold
policy. Its independent observation reader supplies detected / evaluated-no-
detection / unknown outcomes without consuming results awaiting wire delivery.
Failed work is unhealthy unknown; incomplete fractional estimation is healthy
unknown. No scheduling miss becomes a public NO_SIGNAL assertion. The original
SDK entrypoint remains unqualified and its config ABI stays unchanged.

iiOD, the host opt-in, publication binding and UI now support an explicit
`positive-only-v1` profile. The existing extensible mode field is used without
changing published major-v1 layouts or fixed-scan validation. Mode/identity
mismatches preserve legacy capture. The host, presentation binding and UI reject
absence assertions from this profile. Nothing enables it by default.

## Verification

| Lane | Passing checks | Scope |
| --- | ---: | --- |
| Portable Leo | 500 | Policy, record conversion, source binding, CLI, persistence/API |
| Native SDK/worker/host | 222 | All seven worker variants; synthetic positives and independent wire/feedback readers |
| Actual network, unqualified | 16 | Provider/iiOD/libiio/PPU/Leo, including both full 300 s counter spans |
| Actual network, positive-only | 16 | Same transport/failure checks with the explicit new profile |
| libiio configuration | 16 | Default-off, thresholds, malformed inputs and exact SDK linking |
| PPU regression | 299 | Capture and newly merged remote-main regressions |
| Web | 106 + build | Positive-only rendering, invalid absence rejection and existing panels |
| Policy sanitizer stress | 1,280,000 choices | ASan/UBSan/leak checking, 256 masks × two rates × 2,500 visits |

The four early native positive/unqualified host checks are included in the later
222-test lane, not an additional independent sensitivity cohort. The policy
stress executable also cross-compiles for Cortex-A9; it was **not executed on
ARM**. Ruff and whitespace checks pass. Scientific fixtures, numerical
tolerances and the experimental 0.175 / 0.025 operating point are unchanged.

The network source is zero RX1 and constant RX0 with accelerated device time.
It establishes transport and terminal accounting, not positive-signal sensitivity
or realistic worker load. Actual injected positives traverse the SDK/PPU host in
a separate test lane. Neither establishes current live duty, detector quality on
independent RF, or performance of the as-yet-unconnected adaptive hop loop.

## Failures retained and corrected

- Fresh configuration lacked optional Avahi dependencies. The localhost-only
  fixture disables DNS-SD; no system package was installed.
- CMake guessed `-lsdk` for the explicit `sdk.so` artifact. An imported target
  now links the exact supplied file. Tests also prevent ambiguous octal-looking
  threshold literals and emit integer-looking thresholds as floating literals.
- The initial configure-test fixture disabled backends that iiOD requires:
  four failures, 12 passes. Correcting local/XML prerequisites yields 16 passes;
  production validation was not weakened.
- Existing web canvas/deprecation/chunk-size warnings and the API-test dependency
  deprecation remain visible. The relevant commands still exit successfully.

## Remaining work toward the full goal

1. Version adaptive hop requests/events/session receipts and connect the bounded
   SDK feedback to the userspace scheduler. Current fixed-order contracts must
   remain unchanged. The new policy does not yet select physical radio hops.
2. Carry actual variable visits through PPU, storage and Doppler analysis, with
   activity/cooldown/allocation/choice-reason UI. Do not invent complete sweeps
   or assign observations to hypothetical shadow-mode visits.
3. Qualify the frozen decision operating point and exact full-producer package
   on saved data, then measure 300-second ARM load at both rates. The latest
   previous 5 MS/s worker-only copy-to-result p99 of 114.38 ms is **not** a timing
   result for this changed SDK or the complete adaptive scanner.
4. Obtain explicit authorization for bounded live canaries; validate detector
   off/on first, then adaptive/fixed. Verify counter-based duty, IQ continuity,
   revisit/reacquisition behavior, result inventory and cleanup.
5. Review compatible releases, merge, deploy opt-in and verify rollback and
   operation. No remote merge, push or deployment occurred at this checkpoint.

Implementation: Leo `3de0df24`, libiio `df9ef24`; PPU remote-main reconciliation
`222c0b4`. The [execution checklist](../docs/architecture/adaptive-scanner-implementation.md)
preserves the complete objective. [Evidence index](evidence/2026_09_09_adaptive_scanner_policy/index.json)
retains 30 compressed non-IQ/non-executable artifacts, test receipts, exact SDK
and worker source/binary hashes and build attempts. Raw artifacts remain at
`/tmp/leo-adaptive-glrt.VkIAkP`.
