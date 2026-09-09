# Scanner capture-first protection

2026-09-09. Implementation checkpoint, not production deployment or a live-duty
claim. The requested implementation, testing, deployment and verification goal
remains open. No radio, installed software, firmware, FPGA or production service
was accessed or changed for this checkpoint.

## Outcome

An explicit default-off protection profile now connects the acquisition SDK and
actual libiio metadata provider. It limits GLRT admission before the pool fills,
sheds checks under measured callback pressure, and disables a stuck owned worker
without waiting in capture/result/drain calls. Original dual-RX IQ continues to
be returned; an unavailable detector result is never substituted for samples.

| Control | Engineering setting | What it does |
| --- | ---: | --- |
| Pool admission | 2 occupied slots out of 3 | Includes a partially collected dwell; leaves a spare slot |
| Oldest pending job age | 250 ms | Skips new checks before accumulating older work |
| Outstanding-job deadline | 500 ms | Signals only the owned worker and disables this session's detector |
| Metadata callback budget | 80% of source block period | Suspends subsequent checks after an over-budget callback or source-counter gap |
| Recovery | 4 consecutive healthy blocks | Resumes GLRT admission without repeatedly stopping and restarting |

These settings are development values, not measured optimums. For the modeled
131,072-sample producer, the callback budgets are approximately 41.94 ms at
2.5 MS/s and 20.97 ms at 5 MS/s. They must be bound into the trusted release's
configuration identity. No detector numerical threshold, 120 ms valid dwell,
300 s capture duration, channel mapping, RF bandwidth/IF, or 20-minute cadence
is changed.

The companion libiio implementation is local commit `a1088b6` on
`codex/arm-glrt-frame-integration`; the SDK, component tests and receipts are
kept together in this Leo checkpoint. These are compatible source changes,
not an installed release package.

## Evidence semantics and capture ownership

Queue/age shedding emits existing `worker_busy` unavailable evidence. Callback
pressure emits `incomplete_search` with zero search coverage. Both produce an
unhealthy UNKNOWN scheduling observation, not an evaluated miss or an invented
positive. Runtime diagnostics distinguish pressure skips, backlog skips, omitted
history copies, recovery, watchdog trips, clock faults and sampled occupancy
without modifying a persisted major-version contract.

Unknown observations break the consecutive-miss streak and do not refresh a
target's last-positive time. Three globally consecutive unhealthy observations
still latch uniform scanning for the remainder of the capture. Recovering GLRT
does not silently unlatch that fallback. Existing three-miss/two-second cooldown
behavior and source-order binding are unchanged.

When pressure is asserted, only the SDK's advisory RX1 history copy is omitted.
Partial checks are aborted and history is invalidated, so they cannot restart
from stale IQ. Previously submitted results may finish normally. Already
completed evidence is harvested before the outstanding-job deadline is checked.
The watchdog uses monotonic wall time, not device sample counters, and is checked
on subsequent SDK calls, including final drain with no more IQ. It signals only
the session's unreaped child; capture never searches for or waits on processes.
Final reaping is performed during off-capture close.

The provider measures the complete metadata-format callback, including GLRT
collection and framing. This measurement is available **after** the callback;
it cannot prevent that first overrun. It excludes network-send, refill, DMA/IRQ
and other acquisition activity. There is no hard-real-time scheduling or CPU
reservation guarantee, and the worker-priority/full-package settings still need
explicit qualification. The feature is `IIOD_SCANNER_GLRT_CAPTURE_PROTECTION=ON`;
ordinary builds and old SDK entrypoints retain their previous behavior.

## Tests and reproducibility

The new protection suite uses the real SDK and isolated numerical worker with
a test-only linker wrapper for the SDK's monotonic clock. The worker clock is
not wrapped. Exact age/watchdog boundary tests therefore do not depend on
desktop sleep jitter. Production always uses the actual monotonic clock.

- 637 SDK, positive-feedback, protection and native-policy tests pass. The 147
  protection cases cover both rates and all seven numerical variants, stopped
  workers, early admission, exact watchdog boundaries, terminal-only drain,
  clock failure/backward time, partial history, late geometry, hysteretic
  recovery, untouched RX0/IQ, full fractional positives and unchanged fallback.
- 241 wire-contract, codec, result-adapter and host-metadata regression tests
  pass. Published layouts and unavailable-evidence validation are unchanged.
- 23 libiio configure tests pass, including default-off behavior and rejection
  of protection without an explicitly configured SDK.
- All four real desktop provider builds/executions pass: unqualified/positive
  modes crossed with protection off/on. Positive builds include the adaptive
  provider. Hardware I/O is substituted; SDK/worker/provider/policy code is real.
- The protected provider fixture deliberately delays one metadata callback by
  25 ms against a 16 ms budget. Both rates preserve original IQ and opaque
  metadata, report the interrupted check as unavailable, skip advisory copies,
  and resume after four healthy blocks. Separate checks exercise the exact
  budget boundary and sample-gap recovery reset.
- The updated SDK cross-compiles for Cortex-A9/NEON hard-float. This is a build
  result, not new ARM execution evidence.
- The protected positive/adaptive provider and SDK also pass ASan/UBSan with
  leak detection, including the injected callback overrun. The separately
  executed numerical worker and FFTW are not instrumented by this check.
- 16 explicitly marked protected positive-mode TCP/host integration tests pass.
  These use the real iiOD parser, provider, libiio transport/binding and PPU
  host. Both accelerated 300-second source-counter spans retain complete IQ
  and result inventories, final drain and cleanup. Their RX1 IQ is synthetic
  zero; this is not real-time ARM/network contention or live duty. Two existing
  JUnit `record_property` compatibility warnings remain in the test output.

Raw builds and receipts are retained under `/tmp/leo-capture-protection.SsUyjA`.
The [evidence index](evidence/2026_09_09_scanner_capture_protection/index.json)
retains compressed build/run recipes, source hashes, successful JUnit reports,
sanitizer receipts and the failed initial fixture invocation. Executables,
templates and synthetic IQ are not committed.
The initial adaptive provider invocation stopped because its required synthetic
pilot environment was absent. The test setup was corrected by generating its
explicit seeded pilot inputs; the failed receipt remains separate from retries.
No scientific fixture, numerical threshold or expected outcome was weakened.

## Still required before release

Follow-up: both protected 300-second ARM replays and short injected-pressure
checks now pass; see the [protected ARM checkpoint](2026_09_09_scanner_protected_arm_checkpoint.md).
The requirements below record the state at this implementation checkpoint.

The earlier [full ARM replay](2026_09_09_scanner_threaded_arm_checkpoint.md)
predates this implementation. Its 68.98/115.86 ms detector p99 values cannot
qualify the new profile. Repeat protected 300-second ARM runs at both rates,
including deliberate overload, actual queue/memory telemetry and adaptive
transitions. The prior 5 MS/s headroom concern remains unresolved.

Next qualify independent saved-data detection quality and the exact complete
userspace/provider/network/host package. Dense post-capture analysis throughput
at a 20-minute scan cadence remains a separate open gate. With separate bounded
RF authorization, run detector-off/on and fixed/adaptive live comparisons using
source-counter duty and continuity, then complete compatible remote-main merges,
opt-in deployment, real recording/UI verification and rollback checks. No remote
main merge or deployment is claimed by this checkpoint.
