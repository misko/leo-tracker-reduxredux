# Latest-ten phase replay: method and limits

## Selection and provenance

The snapshot begins at **2026-09-27 04:45:39 UTC**. “Fully complete” means a published adaptive recording with completed terminal state and attested sample span, GLRT status `figures_ready`, and tracking status `complete`. The ten newest capture times satisfying these criteria are frozen in [selection.json](selection.json); newer incomplete entries remain recorded as exclusions. This is a snapshot of published adaptive scans, not unpublished spool contents. Production tracking completion can still include catalogue groups deferred by its configured review limit.

All ten captures are from `radio_pluto_5d4d`. The review inventories 22,162 visits and finds 9,552 visits with epoch-matched RX0/RX1 GLRT candidates, of which 779 admit two distinct modes under the metadata gates. “Modes” are distinguishable signal hypotheses, not confirmed separate satellites.

Raw replay is bounded to **195 metadata-selected dwells**. Selection favors at most two recurring RX0 track-pair/channel/edge groups, up to six random visits each, and adds up to six other paired-mode visits and six single-mode visits. It uses seed `2026092705`, before phase extraction. Recurring groups receive a random whole-visit train/held assignment; individual phase windows do not cross that split. Counts and assignments are in [plan.json](plan.json). Each replay also saves its own immutable plan and digest, allowing metadata preparation and raw replay to overlap safely.

Published track membership is checked by reconstructing the default trajectory configuration from the same digest-bound GLRT input and matching exact published track IDs. Unmatched or ambiguous memberships are retained as such. A link to a production track is not a satellite identity confirmation. No new orbit search or production association update is performed.

## Phase extraction

Each selected dwell contributes six non-overlapping 7 ms windows starting at 0, 21, 42, 63, 84 and 105 ms. Templates use the actual sample rate and pilot edge. RX candidates must agree in pilot epoch modulo a frame within 0.3 µs. A second mode must be separated by at least 10 kHz and 0.5 µs, and its inferred receiver CFO difference must agree within 2 kHz.

The two modes share one differential mixing seed per dwell: the median of their GLRT RX1−RX0 CFO estimates. Each RX0 seed remains source-specific. This gives simultaneous modes a consistent receiver phase reference. Independent residual phase rates are then fitted per mode, retaining each midpoint phase intercept. The previous shared-rate experiment did not consistently improve association and is not promoted here.

Pilot templates fit all selected sources jointly with a complex coefficient per source/frame/receiver. Fractional timing searches −0.5, −0.25, 0, +0.25 and +0.5 sample offsets, one coordinate pass, using fitting samples only. Rolled-symbol templates provide controls. The acquisition candidates and timing remain conditioned on earlier GLRT detection; this is not a blind detector-completeness experiment.

Within each window, seed `20261003` partitions 350 physical 20 µs blocks into **175 fitting, 87 source-qualification and 88 phase-evaluation blocks**. Physical block duration is fixed across 2.5, 5, 7.5 and 10 MS/s. All receivers, modes and model comparisons use the same assignment. These blocks are disjoint but residual correlations mean their heuristic z scores are not calibrated false-alarm probabilities.

A source qualifies only if it improves held qualification error in **both receivers**, beyond both the other fitted source and a rolled-target control: positive fractional gain above 1e−8 and z > 3. A single-source fit compares against a zero-source baseline. A pair qualifies only when both constituent sources qualify. Large coherence R alone never establishes source support.

Receiver phase is `arg(RX1 × conj(RX0))` at the common window midpoint, after applying only the training-fitted residual-rate correction. A simultaneous double difference subtracts mode 0's receiver phase from mode 1's. This largely cancels common receiver LO phase. Frequency-dependent response, source-dependent antenna phase, multipath, residual timing error and phase ambiguity can remain. Within-visit mean double difference is a circular mean; its R across qualified windows measures dispersion. Visits with one qualified window have no meaningful across-window consistency estimate.

## Validation and interpretation

Sample-rate and pilot-edge synthetic checks include true two-source phase, absent-source rejection, single-source receiver support, evaluation-sample isolation, and a continuous-time physical RF propagation oracle independent of the extractor's FFT fractional shifter. The oracle includes RF carrier phase, envelope delay, shared LO and independent transmitter frame phases. It is idealized: no noise, hardware filtering or multipath. It does not calibrate the real receiving baseline.

Real negative controls disrupt RX1 alignment on the first qualified two-mode window in each scan, with original timing and frequencies frozen. This posthoc diagnostic is not a population false-positive estimate.

Reported RMS is wrapped training/evaluation disagreement, **not error against known geometry or angular sky error**. Confidence intervals bootstrap whole visits (seed `2026092706`, 2,000 draws), preserving within-visit dependence. Repeated track groups also receive constant-versus-linear circular-phase prediction checks on their preassigned held visits. Sparse circular rate fits can alias; they are not satellite models.

All selected compressed and uncompressed chunk digests are checked through the read-only storage adapter. Clipping counts and exceptions are retained. This does not repeat a complete recording-wide timestamp-contamination audit. No raw data, production tables, collection schedules or public persisted contracts are modified.

The calibrated effective baseline, receiving geometry and independent satellite truth remain unavailable. The earlier DS5 assumption of a 79° axis is not imposed on these newer scans. Unstable adaptive CFO inference and unverified absolute geometric recovery are excluded from this phase replay.

## Reproduction

Use the source revision and pinned replay environment in [runtime.json](runtime.json), `PYTHONPATH` pointing to that checkout's `src`, and one BLAS/OpenMP thread. Run `plan.py`, `batch.py`, `negative_controls.py`, then `summarize.py`. Planning reuses the frozen `selection.json`; do not delete it to silently change the cohort. Plotting additionally requires Matplotlib. Run `python -m pytest test_phase.py` for the scientific checks. The report scripts and artifact digests accompany the results.
