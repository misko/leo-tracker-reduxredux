# Radio .20: passive observer beside native FPGA feedback

The live receiver now runs the coarse observer in a separate ARM thread while
the FPGA/native controller handles scheduled measurements. Firmware-worktree
commit `3948d23fb235de8025e73dae6f8de2a9f3acfd09` passes 307 host tests and builds
for Cortex-A9/NEON. This follows the [observer component qualification](2026_09_13_radio20_passive_coarse_observer.md).
Native feedback still uses its own history and unchanged acceptance gates.

## Composition and sample rates

| Component | Execution location | Input sample rate | Role |
| --- | --- | --- | --- |
| Receive path and decimation | FPGA | 30 or 60 MS/s → 2.5 MS/s | Continuous coarse IQ export with source counters |
| Capture owner | ARM capture thread | 2.5 MS/s | Retain the contiguous IQ ring and publish valid source views |
| Acquisition and catch-up | ARM acquisition worker | 2.5 MS/s | Scan, resolve the original pilot, and build supported history |
| Native measurements | FPGA, controlled by ARM worker | 30 or 60 MS/s | Measure scheduled full pilots and return retained native moments |
| Native feedback | ARM worker | Estimates from the native rate | Update only native history, schedule, drain and recover |
| Passive coarse observer | Separate ARM thread | 2.5 MS/s | Measure 3,300 samples every nine frames, or 12 ms, using independent history |

The observer starts at the acquired history's last-seen frame plus nine. It
retains exact IQ, software moments, estimates and source views in separate
`observer.jsonl` and `observer.iq.ci16` files. Each start references the retained
acquisition attempt and epoch; terminal records distinguish retained records
from committed observations. Cancellation can leave a final retained observation
uncommitted, and that record must not count as support.

The live composition bounds each observer episode to 200 measurements and
three seconds of wall/source look-ahead. Four episodes need at most 10.56 MB
of observer IQ, within the existing selected-capture allowance. Acquisition
attempt, total dwell and reacquisition budgets remain unchanged.

## Timing and lifetime checks

Observer creation and initial evidence retention happen before the native
freshness check. An intermediate test run exposed the risk of doing this work
after choosing the native admission deadline; the final composition avoids
consuming that lead on observer startup.

Every native return, including preflight failure and loss recovery, passes
through observer cancellation and join. Owner destruction or epoch rebase is
prohibited while an observer remains live. The native worker records the join
result before declaring itself finished. Observer source, deadline, I/O or
retention failures fail qualification after native recovery. Observer history
exhaustion and ordinary cancellation remain diagnostic outcomes.

The observer never calls the native controller's read, write or retention
ports. It cannot convert coarse support into native support. Host failure
tests show that a failed observer IQ write is reported while the simulated
native controller still retains and drains all 1,500 scheduled results.

## Host evidence

All 307 tests pass with zero failures, errors or skips. They cover the real
thread composition at both native rates, source publication, exact retained
IQ, cancellation, separate evidence failures, native loss/reacquisition,
unchanged global budgets and joined lifetime before owner release.

An independent review checks 674 observer measurements from four retained
host cases: native operation and loss followed by reacquisition at each rate.
It recomputes integer moments and dense fits from IQ, and independently fits
past history to check timing phase and carrier predictions. Its vectorized
CORDIC is checked against 30,192 scalar cases. Sixteen deliberate mutations of
start, phase step, coherence and IQ offset are rejected. These inputs and
native ports are simulated; they do not establish physical tracking.

The ARM executable SHA-256 is
`f21bafa7c919d24e217b7fa36b9800b69aae45522ec613427a0eb56480be4576`.
Compilation uses Cortex-A9/NEON optimization and treats warnings as errors.

## Physical qualification

The first attempt was refused before radio contact because the shared
acquisition lease was occupied. Its receipt records zero RF samples. Once
that process exited, a second attempt ran on `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`, using the resident 60-MS/s image and a
294.912-second maximum RF dwell. It ended after **226.6245844 seconds**, at
the 200-attempt limit, with zero accepted startup observations and no native
handoff. No observer episode started. Both required observer files are empty,
which correctly records that absence rather than implying a successful test
of simultaneous physical feedback and coarse observation.

Independent review passes 7,332,600 grid scores, 1,600 candidate-order scores,
3,400 resolver hypotheses and 1,600 startup moment/fit records. All retained
overlaps agree across 3,695,883 compared samples. The run exported 566,561,461
coarse samples, returned 566,558,720 in complete buffers and reported zero
CDC/pacer drops. Its maximum refill interval was 10.781376 ms. Identity and
configured RF settings match afterward, TX remains disabled, and the operator
removed its own temporary files. This qualifies the bounded scan and evidence
path for this run; it does not qualify acquired tracking.

## Actual ARM replay after a known handoff

The same radio then executed the integrated acquisition and observer threads
on the existing positive/control recordings, paced at 2.5 MS/s. This used the
actual live observer startup, thread, retention and source-owner functions.
It made no IIO RX or native-controller calls. The replay lets the observer reach
its own bounded terminal state; the host integration tests separately cover
cancellation at native termination.

The positive reached a fresh handoff in **1,412.114 ms**, with 113 accepted
startup measurements out of 118 and 14,393 coarse samples of lead (5.7572 ms).
The observer then committed **37 measurements, 29 supported**, before its
unchanged history horizon stopped further prediction. Total paced elapsed time
was 1,851.560 ms. The control rejected all eight startup measurements, produced
no handoff and left both observer files empty; elapsed time was 1,106.945 ms.

Independent review verifies the original saved-IQ cuts, all 126 startup and 37
observer moment/fit records, both coarse grids, candidate ordering, resolver
hypotheses, imported history, and causal observer predictions. The positive
observer's source IQ matches its original recording exactly. Before/after
attestation is unchanged and temporary files were removed. These are measured
ARM replay times, with a paced saved source; simultaneous real DMA and native
feedback remain unqualified for this integration.

This integration does not establish sustained native tracking, a combined
coarse/native acceptance policy, autonomous frequency revisits or refinement.

The [evidence manifest](figures/2026_09_13_radio20_live_passive_observer/evidence.json)
contains host, live and ARM replay receipts and numerical reviews. Review and
replay source files are retained alongside it. Firmware changes are committed
in the isolated firmware worktree; publishing this report does not imply that
the firmware branch was pushed.
