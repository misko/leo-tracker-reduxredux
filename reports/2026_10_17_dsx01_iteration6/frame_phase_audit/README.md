# Frame-phase provenance: positive arrival phase, unresolved physical interpretation

The surviving original generator uses **positive arrival epoch modulo the frame
period**, not negative arrival phase. Its arithmetic contains no negation.
The saved negative-geometric-range comparison is reproducible, but is not a
definitional sign flip and does not establish Doppler compensation, a hardware
effect, correct satellite identity or a phase-geolocation observable.

The read-only audit rebuilt all four cross-band phase arrays with exactly zero
sample error, all five geometric range arrays with exactly zero error, and
their observed detrended phases within 1.3e−12 samples. It used existing metadata,
frozen historical row selections and frozen geometry, with no IQ reads or new
localization fit. The full audit took 3.71 seconds.

## Located originals and provenance limits

The actual surviving scripts are `/tmp/frame_phase_crossband.py`,
`/tmp/frame_range_consistency.py`, `/tmp/frame_epoch_sign_control.py` and their
setup helper `/tmp/compare_space_track_pipeline.py`. Exact current copies are
preserved in `originals/` with hashes in `audit.json`. The old report had copied
their JSON/figures but not these generator scripts. Its manifest's evidence
hashes match both the report and surviving `/tmp` JSONs byte for byte.

The old report did **not** hash the scripts, so this audit cannot retroactively
attest historical script-byte immutability. Their surviving source, referenced
inputs and independently reconstructed receipts agree semantically. The
`originals/` files are reference snapshots: their setup helper writes old
comparison outputs, so the audit does not execute or import them. `audit.py`
reconstructs their arithmetic through public read-only source/orbit APIs instead.

The source is bound by the old comparison manifest to public baseline job
`dd9c84a33648a347de303cb8345336df`, input digest
`3a79382102760ac8e13f6d093e5b0be6bd168e68df4cb7f292cbf6fd87ebf612`.
Range geometry uses the frozen SPACE-TRACK rerun snapshot
`c1341ed302fe6301e1dd4515e5bcee227d4c0c7aa975bdf572f8f3cbfd702072`,
its original 59-object bank and saved `timing_prior_compressed_0p5s.json` point/
timing vector. These are conditional fitted model states, not independent
geometric truth. No station reference is used to choose a state or identity.

## Counter → epoch → phase

With Fs=2,500,000 samples/s and 750 frames/s, the generator computes:

```
C = valid_start_counter - session_start_counter
    + probe_start_ms * Fs // 1000
epoch = integer_epoch_sample + fractional_epoch_offset_samples
phase = (((C * 750) % Fs) / 750 + epoch) % (Fs / 750)
```

C and both hardware counters remain exact integers until the small modulo term
is formed. The session start counter is 9,256,010,216,565 and observed relative
counters span 444,101–749,460,192. Python integer multiplication avoids fixed-width
overflow. At this Fs, integer milliseconds correspond to exactly 2500 samples,
so the `//1000` probe offset introduces no rounding. The fractional epoch is
added positively after integer counter differencing.

The period is **3333⅓ samples**, or 1/750 s. Delaying arrival by +100 samples
increases this phase by +100 modulo the period. The public source contract
stores the integer anchor and signed fractional offset directly; the public
support-geometry routine indexes samples at `integer_epoch + round(k*period)
+ fractional_offset`. The source projection adds positive local sample positions
to relative hardware counters. The parser adds no hidden sign inversion.
`public_semantics.json` preserves these inspected public definitions and hashes.

The public fractional-acquisition convenience property uses a **rounded 3333-cell
ring** for its acquisition lattice. The report generator does not use that
property: it adds the raw integer/fractional anchor and takes modulo the physical
3333⅓-sample period. None of the 190 distinct audited observations has an integer
epoch within three cells of that acquisition seam. A rounded-frame accumulation
or seam mismatch therefore does not explain the selected negative-curvature
traces. This is not a general validation of every acquisition seam elsewhere.

## Unwrapping and plotting time

The generator applies `np.unwrap(phase*2*pi/period)` then converts back to samples.
All four cross-band traces have **no modulo seam crossing**: unwrapping does not
introduce their negative curvature. Their maximum adjacent changes are 40.14,
43.42, 17.39 and 25.87 samples for CH2/5/6/8, far below the 1666⅔-sample half
period. Largest selected-row gaps are 1.42/2.48/3.90/2.13 seconds respectively.
The local phase branch is numerically stable under the generator rule, but the
unknown transmitted cycle count is not thereby established. A smooth-looking
unwrap is not an absolute clock or frame-number authority.

Cross-band plotting uses each CFO observation's GLRT **support center** as its
time axis. It removes a separately fitted constant (the quadratic's value at
t=185 s) from each channel; cross-band absolute phase offsets are not compared.
The range generator instead uses the **first detected frame epoch**:

```
t_frame = C/Fs + epoch/Fs
orbit_query_time = t_frame + saved_satellite_timing_shift
positive_delay_samples = norm(saved_orbit_position - saved_fitted_site) / c * Fs
```

Support centers are about 8.82–9.48 ms later than the first frame in these traces.
The range comparison removes a separate constant and linear trend from observed
phase and geometric delay, using the first-frame time axis for both. Replaying
this difference changes CH2 observed curvature only from −0.63925511 (support
center) to −0.63924065 samples/s² (first frame); it does not reverse the sign.
Geometry query times all lie inside the propagated bank, without interpolation
clamping. One sample is 0.4 microseconds; detrending destroys absolute phase,
range offset and linear range-rate information.

## Every frozen range comparison

All original groups are retained; the first two alone appeared in the old plot.
These historical IDs/rows are replayed as provenance, not new selection rules.

| Frozen label | N | Span s | Observed curvature samples/s² | Geometric curvature samples/s² | RMS to +range samples | RMS to −range samples |
|---|---:|---:|---:|---:|---:|---:|
| 69522 RX1 CH2 | 38 | 27.68 | −0.63924 | +0.64955 | 38.9586 | 0.3157 |
| 69522 RX1 CH5 | 11 | 12.07 | −0.65766 | +0.69984 | 8.9230 | 0.2806 |
| 69522 RX1 CH8 | 18 | 14.56 | −0.75306 | +0.69601 | 12.7359 | 0.5097 |
| 100168 RX2 CH3 | 75 | 58.56 | +1.60291 | +0.89864 | 346.9291 | 471.8046 |
| 60372 RX2 CH1 | 23 | 53.93 | +0.93748 | +0.57332 | 37.5673 | 140.4057 |

The first three relations are negative, while other traces have positive
curvature and much poorer consistency. A single global phase-negation convention
is not supported. The 100168 trace's maximum unwrapped adjacent step is 1469.65
samples, much nearer the half-period ambiguity limit than the cross-band traces;
smooth-branch assumptions and identity continuity especially need independent
validation there. The CH2 −range RMS of 0.3157 samples (0.1263 microseconds) is a
conditional descriptive residual, not measured range accuracy.

Historical selection matters: CH2's 38 rows came from exploratory quadratic-CFO
continuation with a 400 Hz gate; other groups were selected from a saved CFO
model's winners and fixed time/channel ranges. CFO and fractional epoch also
come from the same candidate evidence. No independent-identity or independent
transmitter-clock test follows merely from adding this second reported field.

## What the positive-delay control establishes

The surviving synthetic control inserts repeated known templates at integer
epochs 500 and 600 with +100 samples of imposed delay. Its saved symbolwise
acquisition returns 500 and 600 and the same +100 kHz CFO. This demonstrates
positive **local acquisition index** response for that control. It does not
establish transmitted frame epochs, cycle identity, receiver clock behavior,
payload scheduling, orbital identity or end-to-end physical delay on real data.
The actual persisted fractional-anchor semantics are separately corroborated by
the public support-geometry source and exact metadata replay.

## Conclusion and validation

The negative comparison is reproducible and **not definitional negative arrival
phase**. It remains an unexplained, selected-evidence relation to a conditional
geometric model. Unknown transmitted frame timing, clock evolution, candidate/
cycle continuity, association and processing effects remain possible confounds;
this audit does not identify any of them as the cause. Do not infer satellite
Doppler compensation or hardware physics from this sign, negate phases globally,
or build a phase-geolocation model from these plots. Such a model needs an
independently justified transmitted-epoch/clock relationship and identity
continuity first.

Four hardware-free tests cover positive delay across a modulo seam, exact
integer differencing beyond 2^53 and multiplication beyond int64, common counter
translation, and nonaccumulating 3333/3334-sample frame-lattice rounding. Replay
assertions separately check all saved phase arrays, descriptive polynomial
coefficients, range arrays and positive/negative RMS values. Only the old
descriptive detrending/polynomial calculations are reproduced; no scientific
state is refit. No original report, production data or raw IQ was changed.
