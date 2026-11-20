# Receiver pipeline evaluation

The goal is a faster, simpler path from stored radio samples to receiver position with the accuracy and coverage of fast v5. The experiment uses existing recordings. The standard roof panel has the eight previously selected DS26 recordings and eight DS29 recordings. Use the original 25 km tile for roof comparisons. The transfer panel retains the earlier four-offer queries and their paired missing-region cases. An independent scorer holds the reference coordinates. Inputs, reference outputs and case selection are frozen before measuring the ten proposals.

## Experiment interface

Implement `tools/pipeline_eval/variants/<name>.py`. Expose `run(case: dict, work_dir: Path) -> dict`. Test in `tests/pipeline_eval/test_<name>.py`. Keep any module-specific helpers under a directory named for the variant. The runner passes a fresh per-case working directory and a dictionary of public input fields:

- `id` is the case ID, `panel` is DS26, DS29, StarLoc, Synthetic, or Altrincham, and `regions` is a list of objects with `id` and `center` in degrees. The inference interface omits the offer condition, truth, previous coordinates, winners, and error metrics.
- `native_path`, `graph_path`, `observation_path`, and `catalog_path` are filesystem paths or null. The graph contains anonymous track points. The observation is a portable projection of those tracks with the fields used by the regional receiver. `native_sha256`, `session_id`, and `run_id` may be available for roof recordings. Use each variant's declared input boundary. A missing input returns an explicit unavailable result. Never replace missing samples with saved detector winners or a previous position.
- Return `status` as `ok`, `withheld`, or `unavailable`, a text `boundary` naming the timed operation, and `metrics` with finite JSON scalars or lists. Put comparable times in `metrics.control_s` and `metrics.candidate_s` in seconds for the same operation on matched inputs. Identify the number of samples, windows, rows or fits measured. Include a `reason` for withheld/unavailable results. The runner also times the complete plugin call.
- A positioning method also returns `arms` with `c0` and `fitted_c`. Each arm has `latlon` in degrees or null and optionally `rf_rms_hz`. A calibration-invariant method may return the same independently computed solution in both arms and declare the invariance in its documentation. For withholding decisions, return only published coordinates in `latlon`; optional `forced_latlon` is diagnostic. Stage-only modules omit `arms`. A bitwise or bounded intermediate equivalence alone does not establish measured end-to-end latency.
- Use `apply_patch` for hand edits. No new RF or hardware access, no modifications under /mnt/qnap01, no oracle use in inference or fitting thresholds to the evaluation labels. Work on one CPU per numerical worker, one BLAS thread. Use small bounded on-disk windows for RF experiments. Keep large scratch and native artifacts outside Git. Only the eval runner scores predictions. Declare any restricted input coverage or stage substitutions.

## Ten hypotheses

| Variant | Change and test |
|---|---|
| iq_stream | Decode recorded IQ in bounded blocks and preserve the samples handed to the detector. Measure data movement and memory. |
| glrt_batch | Batch the pilot bank's matched-filter computation. Compare peak locations, decisions, scores and time on actual IQ. |
| glrt_cascade | Use a cheap first pass to allocate the fine GLRT search. Count saved work, missed positives and noise promotions. |
| track_link | Link detector observations with a causal bounded-state tracker. Carry its tracks through a position solver. |
| track_reduce | Compress tracks using a frequency-error bound, then localize using the same orbit, solver and prior. |
| orbit_interp | Reuse orbital states or interpolate them across nearby times. Check projection error and final coordinates. |
| shape_score | Reduce repeated scoring work in the blind four-region receiver. Compare actual position and withholding decisions. |
| v5_lean | Retain native v5 numerical inference while removing evidence-rendering work from the positioning path. |
| projected_fit | Eliminate nuisance offsets analytically and fit position from independent anonymous tracks and causal orbits. |
| iq_position | Connect recorded acquisition, actual GLRT, track formation, association and a position decision. Keep sparse or missing raw-input outcomes. |

## Decision rules

Use the same recordings and priors for each endpoint comparison. Against original no-repair v5, require at least its fix count and count within 5 km, and median, P95 and worst error no larger than the original in *each* roof dataset and calibration arm. Allow 0.001 km solely for numerical reproductions. Count missing inputs, failures and withheld trials in all-attempt totals. Compare loss of individual fixes and paired error changes, even when a distribution passes. A missing-region coordinate is a failure of geographical withholding. Keep frequency fit separate from localization. A partial stage, prepared inputs, archived answers and full IQ-to-position work have separate labels. A stage speed measurement requires matched before/after work. An embedded real-time claim requires a target-board measurement.

First verify the archived v5 and grid comparison. Run each module on the fixed roof panel and the applicable transfer or raw-input panels. Independently check detections, timed boundaries, and missing-region behavior before ranking. Keep negative experiments in the results. A release qualification additionally needs the original 127-case cohort, independent measured locations, and complete raw-input and target-board timing coverage.
