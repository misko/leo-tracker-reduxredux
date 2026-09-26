# Independent-reference phase recovery prototype

This is a **synthetic observability experiment**, not a claim that an
independent calibration reference exists in the recorded `32a202b6e55630ec`
track.  It tests what could be recovered if both receive paths also observed a
timestamped common reference through a measured injection path.

## Result

The held partition recovers the simulated geometric trajectory when the
satellite cross-product is divided by the aligned reference cross-product after
removing the known injection-path phasor.  `summary.json` contains the measured
held metrics and `recovery.png`/`recovery.svg` plot the result.  The first 40%
of frames are designated training and the final 60% are held.  The recovery
uses no geometric truth parameter and no satellite-derived calibration fit.

The deliberately unsafe comparator fits a smooth polynomial to the satellite's
own recovered phase and subtracts it.  Its small residual excursion is a
failure: the slow geometric trajectory was absorbed into the calibration.

The simulation includes:

- slow known geometry;
- 682.4 kHz receiver-relative CFO plus drift;
- per-tone static phase response;
- a known frequency-dependent injection path;
- satellite and reference noise;
- a known two-frame reference latency; and
- explicit missing/unsupported-reference behavior.

## Algebra and sign

For tone `f` and frame `t`, the synthetic inputs are

```text
S(t,f) = exp(j [geometry(t) + instrument(t) + response(f)])
R(t,f) = exp(j [instrument(t) + response(f) + injection(f)])
```

After timestamp alignment, recovery is

```text
S(t,f) / (R(t,f) / exp(j injection(f))) = exp(j geometry(t)).
```

The injection path must be independently characterized.  Omitting it leaves a
calibration gauge bias; its absolute phase cannot be learned from the satellite
without conflating hardware and geometry.

## Sampling and observability limits

The 682.4 kHz phase term is far above the 750 Hz frame-rate phase sampling in
this simulation.  Sparse phase samples cannot determine the missing integer
cycles or independently estimate that CFO.  Cancellation works here only
because the satellite and reference provide simultaneous (or timestamp-aligned)
complex phasors in the same phase gauge, so the common phase cancels modulo
`2*pi` before any unwrapping or averaging.  A real design needs sample-level
common-reference acquisition, or an independently authorized coarse frequency
and timing solution that derotates both paths into the same gauge.

A delayed reference is usable only when its delay is known and matching
reference samples exist.  This prototype marks missing frames invalid; it does
not bridge them or invent the unobserved cycles.  Its integer delay correction
uses later-delivered samples corresponding to the same physical epoch, which
requires a future buffer (or offline processing); it is not interpolation of a
stale phase. A noisy reference raises the recovered phase noise.

The per-tone division also assumes the injected reference traverses the same
instrumental frequency response at the same RF tones as the satellite. A
reference injected after an unshared filter, LNB, cable, or clock cannot
calibrate that omitted component.

Reference division removes only effects traversed by the calibrated common
paths.  Differential antenna multipath, polarization response, motion, or drift
after the injection point remains indistinguishable from geometry.  The test
suite includes this negative case and confirms that an extra non-common drift
survives calibration.

Absolute geometric phase additionally retains the uncertainty of the measured
injection-path phase and any unknown cable/antenna gauge.  The synthetic primary
metric is nevertheless an absolute wrapped-phase error with no truth alignment,
because this fixture supplies the exact injection phasor.  That favorable result
must not be transferred to hardware unless its injection path and remaining
gauge are independently characterized.

## Reproduction

From the repository root, using the pinned analysis runtime:

```bash
sudo -n env PYTHONPATH=/srv/bulk/leo-dev/scan-32a202-phase-replay/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MPLCONFIGDIR=/srv/bulk/leo-dev/scan-32a202-phase-replay/.mplconfig-coordinator \
  /opt/leo-tracker/releases/2c30eaf50064623a666e1c078c56a02cb3223a70/.venv/bin/python \
  reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/recovery/reference/run.py

sudo -n env PYTHONPATH=/srv/bulk/leo-dev/scan-32a202-phase-replay/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MPLCONFIGDIR=/srv/bulk/leo-dev/scan-32a202-phase-replay/.mplconfig-coordinator \
  /opt/leo-tracker/releases/2c30eaf50064623a666e1c078c56a02cb3223a70/.venv/bin/python \
  -m pytest -q tests/reports/test_recovery_reference.py
```
