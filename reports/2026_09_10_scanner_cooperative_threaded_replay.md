# Cooperative GLRT skips: threaded integration checkpoint

## Outcome and scope

The offline cooperative-skip prototype now passes the actual SDK-to-threaded
libiio policy path at both 2.5 and 5 MS/s. Explicitly shed checks remain unknown,
and injected capture pressure no longer incorrectly latches a scheduler fault.
This is **synthetic-IQ desktop integration evidence**, not an ARM timing,
sensitivity, live-radio, or 300-second qualification result.

The prototype remains on `codex/scanner-5m-cooperative-skips`, not deployed.
There were no firmware/FPGA changes and no new RF collection. The separately
published [report PNGs](2026_09_10_scanner_cooperative_skips_checkpoint.md#web-published-figures)
are deployed in API release `dcaa061d3975e6dd86f14eb3efcc11d7f5674111`.
Acquisition remains on `c60438c5fd096e884a0c523a73097299d1a2f5ba` and its
existing immutable detector bundle: 2.5 MS/s adaptive, 5 MS/s fixed-order.

## What changed

The startup-only cooperative opt-in from the previous checkpoint is unchanged.
A new read-only SDK diagnostic distinguishes its two explicit owner-side skip
causes: pressure suspension and bounded backlog admission. Completed genuine
faults have no intentional-skip cause. The diagnostic does not poll or consume
observations and changes no persisted/wire layout.

The replay executable has a separate `cooperative-skips-v1` profile. Its new
SDK references are optional at link/load time: legacy replay still works when
the two additive exports are absent, while requesting the new profile fails
closed. The compatibility fixture models that older symbol inventory by
renaming only the new exports; it does not execute a historical SDK binary.

The independent replay verifier checks SDK cause, public evidence, health,
monotonic protection counters, visit registration and block-arrival causality.
It does not infer healthy skips merely from an unavailable result. Exact
backlog occupancy and age boundaries are covered by the native port tests,
not independently reconstructed from the threaded replay's sampled counters.

## Tests

| Check | Result |
| --- | --- |
| Native SDK, protection, positive feedback, adaptive policy and frame suites | 910 passed in 77.64 s |
| SDK replay, protected/threaded policy integration and cooperative replay | 185 passed in 119.40 s |
| New cooperative threaded cases, included in the 185 | 28 passed |
| Missing-optional-export compatibility, included in the 185 | Both sample rates passed |
| Cortex-A9 / NEON / hard-float SDK cross-build | Passed, warnings treated as errors |
| Changed Python lint, formatting and whitespace | Passed |

Each new threaded scenario contains 40 visits over 4.84 seconds, with two-block
delivery delay and 40 ms jitter. Tests cover both sample rates with and without
injected pressure, the real isolated numerical worker, the real C policy/queue
and scheduler thread, and an independent Python policy model. They require
complete result/observation/choice inventories, positive detections, weighted
choices and no false fault fallback. Pressure cases require at least three
intentional unknown skips and subsequent admission recovery.

Hostile mutations to profile, cause, health, outcome, counters and timing are
rejected. Native tests retain real watchdog, clock, input and cancellation
failure behavior, unchanged activity/cooldown timestamps for unknown feedback,
and the rule that an already-latched genuine fault cannot be cleared by skips.
No golden scientific fixture was changed.

Run the replay suites with `LEO_LIBIIO_SOURCE` pointing to the matching libiio
checkout (`4323b93a17ff2a0e8954fc5ffd9367a40540bebe` here). They explicitly use
the `libiio_integration` marker and require that source; no radio is involved.
The component test filenames and individual results are preserved in the
[hash-indexed receipts](evidence/2026_09_10_scanner_cooperative_threaded_replay/index.json).

## Remaining release gates

1. Add a default-off provider activation and a newly identified immutable
   bundle configuration; exercise real provider pressure/recovery and genuine
   failure paths. The threaded policy replay is not the full IIO provider.
2. Evaluate fair per-target admission and freshness on saved data. Sparse
   screening must not systematically starve one parity of the eight targets.
3. Measure the same retained RX1 cases on an allowed ARM device and qualify
   any numerical optimization against held-out positive/negative controls.
4. Only then perform a separately authorized bounded live qualification with
   at least 90% valid-IQ duty, bounded result age and honest search coverage.

The earlier 5 MS/s CPU p99 of 172.62 ms has **not** been reduced or remeasured
by this checkpoint. Safe skipping preserves capture priority; it does not make
every-dwell screening below a 100 ms compute budget qualified.
