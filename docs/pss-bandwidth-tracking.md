# Bandwidth-aware PSS acquisition and candidate tracking

The pure numerical APIs live in `leo.analysis.starlink.pss_bandwidth` and
`leo.analysis.starlink.pss_tracker`. They accept arrays and explicit source
coordinates; storage, radio access and HTTP remain outside the analyzers.

**Status: experimental candidate evidence.** Full-bank controls show that
repeating edge pilots can produce both qualified peaks and stable timing tracks.
`candidate_only` is always true. A `tracking` state means a consistent timing
hypothesis, not verified PSS presence, absolute arrival time or satellite identity.
Production PSS acceptance must wait for an independently validated interference
rejection policy. The existing production scanner is not switched to this engine.

## Geometry and template

`PssCaptureBand` separates sample rate, capture-center offset from the published
PSS channel reference, and the usable baseband interval. The latter may be
asymmetric. Optional complex response knots describe a known receiver filter.
Without them, the model assumes an ideal rectangular passband; sample rate alone
does not measure the radio's analogue response.

For each CFO hypothesis, the engine intersects this passband with the shifted
240 MHz PSS channel. It evaluates the published waveform's filtered spectrum
on the original sample grid. Frequencies outside the intersection contribute
nothing. A partly overlapping capture is supported without throwing away its
in-channel bandwidth. A completely disjoint capture returns explicit unsupported
hypotheses. Extremely narrow overlap requires sufficient quadrature resolution
and observable template energy; it is not silently normalized into a detection.

The implementation uses 16,384-point spectral quadrature and retains the
published 4.4 microsecond symbol aperture. This is a finite-aperture model,
not an infinite-duration impulse-response simulation. Quadrature convergence
and an independent high-rate IFFT reference are tested. Long instrument filter
tails and absolute instrument delay still require separate characterization.

Rates in `(0, 240 MS/s]` are supported without an integer decimation requirement.
The CFO bank has at most 257 distinct hypotheses inside sampled Nyquist. These
are declared observable coordinates, not support for resolving arbitrary aliased
carrier offsets. Each hypothesis performs its own blind timing search. The
legacy timing function's frequency list alone performs only post-acquisition
frequency refinement; it is not equivalent to this bank.

`acquire_pss_coarse_to_fine()` adds a bounded fine search around up to four
strongest coarse hypotheses. It never repeats a searched CFO and preserves
every coarse and fine result. The eight-hour bandwidth comparison deliberately
uses the same fixed bank in both arms to keep their search budgets comparable.

## Minimal integration

```python
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.analysis.starlink.pss_tracker import PssTracker, observations_from_search

band = PssCaptureBand(
    sample_rate_hz=10_000_000,
    center_offset_hz=115_195_312.5,
    passband_low_hz=-5_000_000,
    passband_high_hz=5_000_000,
)
source_key = "capture:clock-generation:rx0:ch1upper:geometry-digest"
tracker = PssTracker(source_key)
blind_bank = tuple(float(f) for f in range(-1_200_000, 1_200_001, 200_000))

# iq must be one valid continuous block. Never concatenate across retune gaps.
result = acquire_pss_band(
    iq, band,
    device_sample_start=source_relative_counter,
    continuity_segment_index=visit_index,
    frequency_offsets_hz=blind_bank,
)
block_time = (source_relative_counter + len(iq) / 2) / band.sample_rate_hz
estimate = tracker.update(source_key, block_time, observations_from_search(result))
assert result.candidate_only and estimate.candidate_only
```

Use separate trackers for different receivers, channel edges, sample geometries
and clock generations. Use a fixed source-relative counter origin to avoid
precision loss from floating-point UTC. Supply device-counter gaps faithfully.
Projection adapters must account for resampling phase, trims and filter delay.
The engine keeps no cross-block FIR or coherent phase history.

## Tracking policy

Two constant-rate Kalman filters predict frame phase and coarse CFO. Timing is
circular with the published frame period. Each update uses only earlier state
and current observations, retains uncertainty, rejects distant observations,
and abstains when competing modes have similar scores. States are `acquiring`,
`tracking`, `coasting`, and `lost`. A long gap or repeated misses expires the
association and allows reacquisition. Out-of-order data and changed source keys
are errors. Statistical predictions across gaps do not claim observed continuity.

Default gates and process-noise values are explicit engineering policies, not
calibrated probabilities. Timing uncertainty has a one-sample floor; coarse CFO
uncertainty has a bank-step floor. Neither is a claim of calibrated accuracy.
`frequency_bank()` suggests a narrower future bank after lock; the caller must
retain periodic full-bank reacquisition. Temporal cropping around a predicted
epoch is not implemented, so input blocks still undergo a full timing search.

## Validation and reproduction

Run the component and compatibility tests:

```bash
python -m pytest tests/analysis/test_pss_bandwidth.py \
  tests/analysis/test_pss_tracker.py tests/analysis/test_pss_timing.py \
  tests/analysis/test_pss_search.py tests/analysis/test_standard_native_pss.py
```

`tools/replay_scanner_pss_bandwidth.py` reads sealed adaptive IQ through its
read-only storage adapter. It preserves the frozen report's manifest digests and
selects visits independently of outcomes. It compares native 10 MS/s with the
existing ideal FFT-derived 2.5 MS/s projection, separately from online GLRT's
161-tap Q15 decision path. It never starts RF acquisition or publishes products
to production stores.

`tools/qualify_pss_bandwidth.py` runs the same 120 ms/full-CFO-bank budget on
noise, tones and pilot-only waveforms. Its false candidates and false candidate
tracks remain in the report. Future acceptance changes require independent
controls rather than tuning the threshold to remove this particular result.

Existing persisted contracts and golden waveform fixtures remain unchanged.
The timing kernel has one additive optional `template_samples` argument;
omitting it retains the previous template and numerical path.
