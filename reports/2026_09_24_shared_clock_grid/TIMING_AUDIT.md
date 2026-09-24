# Read-only timing convention audit

## Finding

No deterministic half-second convention appears in the observation or cached-state path. The `tau=-0.5 s` preference at the three benchmark points remains a hypothesis-generating result, not evidence of a clock correction. The plausible unresolved causes are catalogue/orbit phase error, candidate-selection changes, position/tau coupling, or an absolute timing bias outside the recorded host bracket model. This audit did not search any new numeric parameter, use truth, or inspect VAL/TEST.

## Observation timestamp authority

The fit does not timestamp a GLRT response at probe start, visit start, integer epoch alone, or the end of a one-second bin.

1. `src/leo/application/scanner_trajectory.py::project_scanner_candidates` obtains the support geometry for each passing fractional GLRT candidate. It forms an integer `relative` device-counter displacement from the session counter, visit valid-start counter, and probe offset. Its local `utc()` adds the fractional support location, converts at the recorded sample rate, and adds `timing.first_sample_estimate_utc_ns`.
2. `src/leo/application/persistent_hop_trajectory.py::fractional_glrt64_support_geometry` enumerates the actual GLRT OFDM-symbol intervals for every usable frame. Each interval center is `continuous_start + (count - 1)/2`; `center_in_probe_samples` is the arithmetic mean of all those centers. This is the timestamp written as `support_center_utc_ns`.
3. `src/leo/operations/adaptive_tle_position_inputs.py::prepare_adaptive_tle_position_inputs` sorts graph observations by `support_center_utc_ns` and defines `track.times_s = (support_center_utc_ns - first_sample_estimate_utc_ns)/1e9`. Thus the cache query and measured CFO refer to the same support center.

The older `src/leo/scanner/persistent_hop_analysis.py::glrt64_cfo_observation` constructs a `TrajectoryObservation.time_s` at the detected epoch sample. That legacy object is not the authority consumed by this cache: the cache calls the public preparation operation, which uses `project_scanner_candidates` and its fractional support-center UTC. Confusing these two paths could suggest a centering issue, but the executed cache receipt binds the latter path.

The observed support windows are millisecond-scale. For example, strict recovered metadata for the first TRAIN session contains support start/end spans near 9.5 ms, not 1 s. A start-versus-center mistake at this layer would therefore be millisecond-scale and could not directly supply a fixed 0.5 s shift.

## Absolute UTC authority

`src/leo/scanner/persistent_hop.py::PersistentHopUtcTimingAuthorityV1.from_host_bracket` constructs the first-sample estimate as the integer midpoint of a host realtime/monotonic bracket. It records the earliest/latest endpoints and verifies them on contract load. Read-only inspection of the original public manifests for the twelve experiment scans found:

- first-sample bracket widths: **1.196–1.635 ms**;
- half-widths: **0.598–0.818 ms**;
- realtime/monotonic offset spreads: **0.425–1.209 microseconds**.

These recorded bounds rule out a half-second offset arising from choosing the midpoint rather than either bracket endpoint. They do not prove the host realtime clock was absolutely correct: a systematic host-clock error common to all bracket samples would survive this construction. The persisted evidence has no external UTC calibration capable of testing that hypothesis, and the shared-clock protocol correctly describes tau as an uncalibrated sensitivity.

## State cache and velocity epoch

`reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py` builds an integer one-second grid that covers all rounded `track.times_s + tau` queries. It calls `propagate_candidate_states` with `prepared.start_utc_ns` and those relative offsets.

`src/leo/analysis/adaptive_tle_prediction.py::propagate_candidate_states` constructs exact UTC nanoseconds as `start_utc_ns + round((time + tau)*1e9)`, propagates SGP4 at those instants, computes GMST at the same instants, and converts both position and velocity from TEME to ECEF. `src/leo/sky/propagation.py::propagate_grid` receives position and velocity together from `SatrecArray.sgp4`; velocity is not a forward or backward finite difference. `src/leo/sky/frames.py::teme_to_ecef` rotates that instantaneous velocity and adds the `-omega × r` term for the co-rotating frame at the same epoch.

`reports/2026_09_24_shared_clock_grid/run.py::Engine.interpolate` linearly interpolates both arrays at `track.times + tau`. There is no implicit `+0.5 s` center applied to a one-second cell. Linear interpolation can introduce small curvature error, but the sealed direct-SGP4 audit in `reports/2026_09_23_long_training_selected_interpolation_audit/README.md` measured only 0.028 Hz median and 0.074 Hz maximum per-track Doppler-shape RMS after the same training CFO profiling. That evidence is incompatible with cache interpolation acting like a wholesale half-second epoch displacement.

One implementation detail deserves care: `run.py` converts integer nanosecond grid offsets to float seconds before interpolation. At these relative offsets (hundreds of seconds), float precision is far below a nanosecond and cannot create a half-second displacement. The absolute UTC remains in the states already generated by the cache exporter; it is not represented as a large float epoch here.

## Interpretation of the benchmark

The three points sharing `tau=-0.5 s` shows an organized local loss preference. It does not identify its cause because the benchmark jointly reselects the best candidate per track at each tau and profiles a constant CFO. A shared tau can absorb common catalogue phase, position error, or absolute receive-time error, while candidate changes can make its loss profile non-smooth. The benchmark grid itself has 0.25 s fine spacing, so the repeated `-0.5 s` value is a selected grid point rather than a sub-grid clock estimate.

The next interpretation should use the sealed full-grid result and its already-prespecified diagnostics: check whether the optimum is stable across geography, TRAIN blocks, receivers/RF lanes, fixed-candidate versus reselected-candidate scoring, and whether it reaches the ±5 s boundary. Those checks distinguish stability and confounding; they still cannot convert tau into a calibrated clock correction without independent UTC or orbit evidence.

## Read-only evidence used

- Twelve original capture timing manifests, read through `AdaptiveHopIqStore` as service user `leo`.
- The two frozen TRAIN cache-selection manifests and their first six session IDs.
- Existing cache exporter, input preparation, fractional GLRT support geometry, propagation, ECEF conversion, and shared-clock evaluator sources.
- Existing sealed direct-SGP4 interpolation audit.

No source, cache, RF data, live experiment file, or production component was modified by this audit.
