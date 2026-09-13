# Radio .20: causal carrier prediction during startup

A small startup change recovers all eight required initial measurements from
the exact retained IQ of the previous near-acquisition. The old C implementation
reproduces the recorded six-of-eight result; the new C implementation accepts
eight of eight without changing coherence or local-correction thresholds.
Later catch-up IQ was not retained for this candidate, so this result does not
prove a fresh handoff or native tracking.

Firmware-worktree commit `ebca81d4e440b1bf3b371df72bd6c38a1d1dced0` implements
the change. All 322 relevant component tests pass. This update collected no RF.
The planned ARM replay and physical 30-MS/s check could not start because radio
`.20` became unreachable during identity preflight; no updater was dispatched.

## What the retained data showed

The [previous bounded run](2026_09_13_radio20_bounded_reacquisition.md) selected
coarse rank one on attempt 160. A post-hoc three-repeat timing/frequency search
on all eight retained basins confirms that this candidate is much stronger:
its best coherence is 0.0471, versus at most 0.00203 for another basin.
Only three complete repeats are available for every unselected basin, so this
diagnostic does not replace the required four-repeat resolver.

The initial bootstrap takes a measurement every nine frames, or 12 ms. Before
eight observations are available, it previously held the most recently
accepted frequency constant. On this candidate, frequency decreases by about
377 Hz over 84 ms. After the first rejection, the held prediction grows older,
which further reduces coherent matched energy on the next pilot.

Re-estimating frequency separately on each saved pilot can recover the two
failed measurements. That exploratory FFT search is post-hoc; it was not added
to runtime. Instead, the implementation predicts carrier drift using only
earlier accepted bootstrap measurements.

| Initial measurement | Original coherence | Causal-prediction coherence | Result |
| --- | ---: | ---: | --- |
| Frame 45 | 0.049097 | 0.050256 | Rejected → supported |
| Frame 54 | 0.046952 | 0.052273 | Rejected → supported |
| All eight initial measurements | Six supported | Eight supported | Initial history requirement met in replay |

The remaining six measurements stay supported. The replay uses the exact
retained windows, without padding missing samples. Independent dense fits
verify all eight new results, and a separate least-squares check verifies the
five early carrier forecasts. Corrupted forecasts are rejected by that reviewer.

## Runtime behavior and bounds

For initial jobs 3 through 7, the ARM can fit frequency against frame using
three to seven earlier accepted observations and predict the next scheduled
carrier. Every previous startup job must have been accepted. The forecast is
limited to the next nine-frame step and must remain within 250 Hz of the last
accepted carrier and inside the existing Nyquist guard. Otherwise startup
keeps the previous hold-last behavior.

This adds no per-pilot FFT, phase search or future measurement. The first three
jobs keep their existing behavior. The coherence gate remains 0.05, local
correction bounds remain unchanged, and all eight initial observations are
still required before full-history prediction or a future handoff.
Timing propagation, source and wall-time budgets, five-millisecond handoff lead,
and the last-supported-plus-32-frame horizon are unchanged.

This addresses a measured carrier-prediction limitation. It does not resolve the
separate coarse/native coherence difference or qualify weak native signals.

## Validation and its limits

The 322 passing component tests include signed frequency ramps, constant
carrier, rejection fencing, forecast/Nyquist fallback, source association,
retained-IQ worker behavior, bounded reacquisition and simulated native feedback
at 30 and 60 MS/s.

On twelve existing historical replay cases, the full worker preserves every
prior disposition: seven of eight selected historical positive cases reach a
fresh proposal, one remains rejected, and all four controls reject. This replay
uses real saved IQ with explicitly modeled ARM processing costs: 840 ms for
scan/order, 600 ms for resolution and 2.5 ms per past measurement. It is a
development comparison, not held-out detection calibration or measured ARM
performance.

A separate actual pthread/FFTW replay on this host paces saved IQ at 2.5 MS/s.
The positive case accepts eight observations and reaches a fresh handoff in
87.067 ms, with 14,095 samples (5.638 ms) of lead. The control rejects.
Independent review checks all 73,326 grid values, sixteen ordering scores,
34 resolver hypotheses, sixteen moment/dense-fit comparisons and exact retained
IQ. It also checks the five startup forecasts on the positive case.
These elapsed times are **host measurements**, not ARM timings; no native jobs
or radio I/O occur.

## Deployment status

The target remains `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`. The ARM live probe and paced-replay binaries
build successfully with Cortex-A9/NEON optimization and warnings treated as
errors. Their SHA-256 values are:

- Live probe v11:
  `284b392d5199a58dc82eab0678816b82742e453849915b5dd51e2740c184952a`
- Saved-IQ ARM replay:
  `45d71aee995efae34367b4eebc0a6a6efb0a8ca6ec28fda0bc74559b428bed01`

The 30-MS/s image inputs passed local verification, but deployment failed in
`prepare_lan_flash_plan` while reading LAN IIOD identity. The attempt directory
contains no plan or updater receipt. At 03:25 UTC on September 13, SSH and IIOD
connections still fail, the neighbor entry is FAILED, and the host interface
and gateway remain reachable. This attempt sent no firmware update.

The last successfully attested resident image was
`glrt-iq-tracking-r60000000-v1`; its current state cannot be reconfirmed while
the radio is unreachable. Actual ARM execution of this change, updated physical
tests at both rates, supported native restart, sustained feedback, autonomous
frequency revisits and longer refinement remain unfinished.

Evidence is retained beneath
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.
The [evidence manifest](figures/2026_09_13_radio20_causal_startup_carrier/evidence.json)
contains the frozen development plan, exact-IQ diagnosis, C replay, independent
checks, test receipt, host replay, network preflight and source/binary hashes.
