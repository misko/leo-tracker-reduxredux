# Radio .20: ARM startup qualification and deployment status

This report records the first saved-IQ stage. Subsequent firmware builds,
flashes and bounded RF tests are documented in
[native 30/60 MS/s commissioning](2026_09_12_radio20_native_30_60_commissioning.md).
Its resident-firmware checkpoint supersedes the v0.49 state described below.

The first implementation stage was deployed temporarily to radio `192.168.1.20`
and exercised on its actual ARM CPU using retained physical IQ. The full
autonomous FPGA/ARM tracker was **not deployed**. No new RF collection, retune,
FPGA reconfiguration, firmware flash, or service installation was performed.

The new command takes the existing production capture lease and PPU serial
lock, verifies the recorded SSH key and radio identity, stages hash-checked
files in RAM, runs a bounded numerical benchmark, and removes its temporary
files. It checks boot identity, the firmware partition hash, RF settings and
idle buffers before and after. The resident v0.49 capture firmware remained
unchanged, and TX LO remained powered down.

## Measured on .20

| Measurement | Result |
| --- | --- |
| Radio serial | `1040005e0b100007100010000bf33a5d4d` |
| Resident firmware | `v0.49-plutoplus-spf-iq-direct-async-v4` |
| Retained-IQ processing rate | 2.5 MS/s, four pilots per resolver input |
| Frozen development cohort | 14 cases: eight accepted acquisition cases, six controls |
| Fresh handoffs | Three of eight accepted cases; case indices 1, 2, 3 |
| Unsupported accepted cases | Five; case indices 5, 8, 10, 12, 13 |
| Control handoffs | Zero of six |
| Full resolver duration | 513–723 ms across the 14 cases |
| Resolver plus catch-up, successful cases | 932.44, 934.31, 954.91 ms |
| Process deadline | 45 seconds, enforced inside the ARM executable |
| Radio state and firmware partition | Identical before and after |
| Temporary deployment | Removed after evidence retrieval |

Each resolver checks all 17 timing hypotheses against retained expected
frequency/coherence values. Each consumed past-pilot job checks its exact
sample/phase association and all 16 integer moment words before updating the
tracking state. Source availability advances with elapsed ARM computation time;
this is not an offline oracle supplying an already-current tracking seed.

The benchmark reproduces the existing numerical baseline. That is distinct
from qualifying live tracking. The fixtures are preloaded sparse IQ, so the
timings exclude live DMA ingestion, recent-IQ buffer contention, detector
execution and final hardware submission. They do not establish absolute
timing/frequency accuracy or a representative acquisition success probability.
Not every coarse accepted candidate must be trackable, but all unsuccessful
handoffs must remain visible and the live rejection/reacquisition policy still
requires qualification. No thresholds or forecast expiry were relaxed.

Evidence: [ARM output](figures/2026_09_12_radio20_tracking_qualification/arm-output.json),
[radio receipt](figures/2026_09_12_radio20_tracking_qualification/receipt.json),
[payload/source manifest](figures/2026_09_12_radio20_tracking_qualification/manifest.json),
[byte-identical rebuild and supplemental include hash](figures/2026_09_12_radio20_tracking_qualification/build-reproduction.json).

## A stronger historical hardware checkpoint

The earlier report synthesis emphasized the 192 scheduled jobs. During this
implementation work, the external September 10 `.20` acquired-controller
receipt was located and its journal independently re-read through the current
GLS1 journal reviewer. Its SHA-256 matches the retained operator receipt:
`78d375ce2d681f16305180d9c470abf30c26a96021acd3b1f85a3e00361dfe5d`.

That journal contains 10,463 returned measurements, of which 10,431 passed the
recorded support gate. It accounts for 655 descriptors, zero late/expired/
unavailable jobs, zero source-path drops, and complete final drain. The
historical operator reports about 14 seconds of ARM feedback before support
loss. It used host-assisted acquisition and a 60-MS/s native FPGA engine;
it was not a fully radio-local autonomous service.

This is stronger integration evidence than the initial 192-job checkpoint and
corrects the earlier impression that only isolated scheduled jobs had worked.
The new audit validates journal structure, association and accounting, not a
fresh RF run or independent physical accuracy. It does not rerun every
historical ARM/host numerical comparison.

Evidence: [new journal review](figures/2026_09_12_radio20_tracking_qualification/historical-native-journal-review.json).
Original evidence is under
`/srv/bulk/leo/glrt-deployment-20260909/native-acquired-controller-20-v3/`.

## Remaining work recorded at the first-stage checkpoint

The tested new ARM seed/worker uses the direct 2.5-MS/s upper-edge GLA1/GLT1
path. The reusable historical native hardware uses the 60-MS/s GLS1 path.
Joining these requires qualified source-epoch, filter/template and rate
mapping plus loaded admission checks. Multiplying a timestamp by 24 is not
the complete handoff. The existing host-assisted native path is a useful
reference for this integration, but it does not supply the missing ARM-only
acquisition handoff.

Radio `.20` currently exposes the production capture devices and no
`schedule_*` or `tracking_*` attributes. The reviewed combined local-search/
tracking FPGA image has not passed full-board routing/timing. Consequently,
there is no qualified complete new receiver to substitute for the production
image in this work. Flashing the historical image alone would not implement
the requested new acquisition/catch-up/controller chain.

The next implementation milestone remains one acquired loop with live source
coordinates, loaded handoff, every-frame accounting, explicit loss handling,
and one qualified FPGA configuration. Sequential scanning and slower
multi-frame refinement follow that milestone. The user's authorization covers
radio `.20` implementation and deployment; the remaining issue is engineering
qualification, not a missing approval.

## Implementation and validation

- [Operator command](../tools/qualify_radio20_tracking_bootstrap.py): explicit
  `.20` binding, normal ownership, pinned SSH key, payload integrity, finite
  execution, result assessment, cleanup and retained receipts.
- [ARM benchmark](../tools/glrt_tracking_replay_bench.c): versions the existing
  saved-IQ benchmark and adds an internal 45-second alarm. Compile it with the
  firmware's resolver, IQ moments, solver, trend and schedule components;
  the exact build command is retained in the manifest. The linked firmware
  checkout is `705d74a639e517334ee8f6c914b2e4ebcf6dbc7d`.
- Twenty new operator assessment tests passed, including incomplete evidence,
  stale handoffs, false-positive controls, wrong device, active buffers,
  TX state and payload damage. Ruff passed for the two new Python files.
- 124 existing resolver/catch-up/live-worker/native-controller tests passed.
  An initial sparse-checkout test attempt lacked the coefficient submodule;
  the affected 55 tests were rerun successfully in the complete checkout.
- The first radio preflight found that BusyBox lacks `timeout` and stopped
  before staging. The internal alarm removed that dependency. The refusal
  receipt is preserved alongside the successful run.
- A second compilation reproduced the executed ARM binary byte-for-byte.
  Its supplemental record includes the native Gram include omitted from the
  first manifest inventory; the original manifest and receipt were preserved.

The qualification runner intentionally reports `replay_verified` separately
from `live_tracking_qualified=false`. It installs no background receiver and
never converts a partial numerical success into a deployment claim.
