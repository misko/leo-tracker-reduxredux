# DS5 server-first GLRT evaluation

Started 2026-09-26; final held-out evaluation completed 2026-09-27 UTC.

Three GPT-5.6 SOL workers built the dataset, explored timing-search strategies,
and evaluated decision-band decimation. Root reviewed scientific comparisons,
froze source/configuration/build/dataset hashes, ran both final held-out jobs
sequentially on server CPU 2, and integrated original-arrival cost replays.

**Outcome: the evaluation system is ready; neither tested implementation earns
ARM promotion.** Seeding with fallback preserves reference evidence but adds
work. The direct FIR decimator passes synthetic fidelity checks but is expensive
and changes which observation window is selected. Causal tracking-derived
prediction remains a distinct next experiment; it was designed, not implemented
or validated here.

## Evaluation design

Read [PROTOCOL.md](PROTOCOL.md) for the full preregistered procedure. Each
experiment proceeds through development, configuration/source freeze,
validation, and one final held-out run. Performance is reported alongside
exact/control scores, supported/unknown status and matched candidate identity.
Reference-positive means fractional confirmation completed and margin >0.025.
The primary matching rule requires the same 20-ms observation window, CFO
within 8 kHz and circular timing within 2 microseconds. It is reference-relative
evidence, not physical ground-truth recall.

The [common evaluation core](evaluation_core.py) and
[integration tool](integrate_results.py) preserve unsupported cases and replay
original source arrivals. Both receiver service costs are summed per visit;
completion age includes the 120-ms acquisition interval. Measured server
medians are used directly, without inventing an ARM scaling factor.

Two native build helpers use different scientific profiles. The search worker
uses the older native-tone-CI16 profile, while the decision-band worker uses
the decimated-replay profile with additional ranking/diversity/energy-support
features. Their baseline detections differ on identical IQ. Comparisons below
are within each unchanged build; positive denominators and absolute performance
must not be pooled across families.

## Frozen dataset

[Dataset manifest](dataset/cases.json), [selection plan](dataset/selection_plan.json),
[builder and loading instructions](dataset/README.md).

| Cohort | Visits | Receiver cases | Coverage |
|---|---:|---:|---|
| Development | 32 | 64 | 8 visits at each of four rates |
| Validation | 32 | 64 | Separate sessions, same rate balance |
| Holdout | 32 | 64 | Separate sessions, one final test |
| Synthetic controls | 24 | 48 | Four rates × two edges × pilot/noise/tone |

Each real case is an original 120-ms visit containing both receivers. The
96 real cases span 12 sessions and 11.52 seconds of valid recorded exposure.
Contiguous eight-visit blocks preserve source-counter gaps and retunes.
All channels and both edges are represented within every split, but rate ×
edge is not fully crossed. Each rate/split has only one session and one edge.
The two sessions used in the earlier speed probe are absent from this suite.

Selection used frozen inventory, hashes and target metadata, not detector
scores. Real cases are unlabeled; a reference miss is not a negative. Synthetic
controls have 48 distinct receiver seeds and explicit construction truth. They
are smoke/fidelity controls, not rare-false-alarm calibration or representative
weak-signal coverage. Local materialized arrays occupy 720,015,360 bytes
(approximately 687 MiB) and are ignored by Git; the recipe and hashes remain.

Cases manifest SHA-256:
`ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`.
Archive manifest, compressed chunk, decompressed IQ and local NPY hashes were
verified. A metadata-only builder-hash revision and preliminary development
exposure are disclosed in [the search record](search/PRELIMINARY_EXPOSURE.md).
No validation or holdout outcomes were used in that revision.

## Search/proposal results

[Worker report](search/REPORT.md), [frozen configuration](search/frozen_validation_config.json),
[held-out raw results](search/holdout_results.json).

Development tested direct 512-bin seeding, two finer timing grids, a multi-seed
union, and two blind-fallback policies. The fast direct seed retained only 1/6
development reference positives. The two finer grids retained 3/6 and 4/6.
Fallback retained all references but did not save total work.

| High-resolution seed + blind fallback | Matched reference positives | Median native CPU per RX, baseline → candidate |
|---|---:|---:|
| Development | 6/6 | 1.236 → 2.099 ms |
| Validation | 12/12 | 1.135 → 1.544 ms |
| Final holdout | 17/17 | 1.160 → 1.293 ms |

Final holdout CPU cost increased about 11.5%; median wall increased from
1.237 to 1.369 ms per receiver. The binding evaluates only 2.5 and 5 MS/s;
the other 16 real visits in each split remain explicitly unsupported.
On supported synthetic controls, both baseline and fallback recover 3/8 known
pilot receiver cases and produce zero noise/tone gates. This baseline weakness
is retained rather than hidden by changing controls or claiming 3/3 truth recall.

## Decision-band results

[Worker report](decision_band/REPORT.md),
[frozen configuration](decision_band/config.frozen.json),
[held-out raw results](decision_band/holdout.json).

The candidate uses a causal Q15 anti-alias FIR and 2.5-MS/s blind GLRT.
Timing is mapped back with the FIR group delay removed; incomplete startup
support is masked and boundary-unsupported results stay unknown. All filtering,
receiver extraction, screening and confirmation costs are included.

| Final holdout source rate | Primary same-window retention | Mean wall per dual-RX visit, baseline → candidate |
|---|---:|---:|
| 2.5 MS/s | 14/14, identity path | 3.125 → 3.159 ms |
| 5 MS/s | 0/3 | 6.008 → 24.339 ms |
| 7.5 MS/s | No native-rate oracle | Unavailable → 35.794 ms |
| 10 MS/s | No native-rate oracle | Unavailable → 39.883 ms |

**The 5-MS/s matching failure is not proof of signal loss.** All three proposed
positives use different 20-ms windows. Their CFO differences are approximately
179–241 Hz and circular timing differences 0.10–0.37 microseconds, within the
frequency/timing bounds. They still fail the frozen same-window endpoint.
Validation similarly retained only 1/8 under that endpoint. A next experiment
must hold the observation window fixed to isolate detector changes from ranking
changes, or predeclare a valid cross-window trajectory association. We did not
relax the criterion after seeing holdout.

All 16 injected pilot receiver cases were detected across the four rates;
maximum truth-relative CFO error was 49.3 Hz and timing error 0.130 microseconds.
The 16 noise and 16 tone receiver controls produced zero positives. This
qualifies only these finite constructed inputs. There is no native-rate quality
claim for 7.5 or 10 MS/s.

The direct FIR is roughly four times slower than native 5-MS/s processing in
this server implementation. Lower sample count alone did not produce a win.

## Arrival replay and verification

[Search holdout replay](search_holdout_results_integrated.json) and
[decision-band holdout replay](band_holdout_integrated.json) preserve the actual
visit inventory. Search processes 16/32 visits and marks 16 unsupported;
decision-band processes all 32 but lacks a high-rate quality oracle.
No queue accumulated in these short server replays. Maximum completion age was
126.1 ms for fallback and 160.1 ms for decision-band, including acquisition.
Each block starts with an empty queue and contains only eight visits: these
figures do not qualify sustained load, burst resilience or p99 latency.

- 40 tests passed across dataset integrity, metrics, arrival replay, search
  identity/configuration, decimation alias/delay/support and input immutability.
- All hashes in [the pre-holdout freeze](holdout_freeze.json) remained unchanged.
- Timed finalists ran sequentially on CPU 2, with one warmup and three measured
  repetitions, bounded by 180-second process deadlines. No RF was collected.
- Whole-suite Ruff passes with E501 excluded. The frozen search snapshot has
  three long-line style diagnostics; it was not reformatted after qualification.

Run the tests with:

```sh
.venv/bin/python -m pytest -q reports/2026_09_26_ds5_server_eval
```

Each worker report includes exact reproduction commands. Existing receipts are
evidence; use new output filenames for reruns and do not call this now-exposed
holdout a fresh test of newly tuned variants.

## Next experiments and ARM gate

1. Implement [the causal tracking plan](CAUSAL_TRACKING_PLAN.md): previous
   confirmed timing, state keyed by receiver/channel/edge/rate, age and
   innovation bounds, and blind reacquisition. The present dataset has enough
   repeated targets for a one-step feasibility test, not long-track validation.
2. Benchmark an optimized existing FFT/staged decimator against the direct FIR,
   including filtering cost and the same support convention. First compare
   confirmation on fixed source windows to avoid conflating changed rankings
   with lost signals.
3. Move the finalists onto one explicitly shared detector profile and a newly
   frozen test version. Do not choose an apparent winner across these two
   different baselines.
4. Only variants that retain required evidence, pass controls and reduce total
   server work advance to short saved-IQ ARM measurements. Verify the target
   processor/build and capture-load conditions; desktop timing is not ARM timing.

The adaptive scheduler remains a design-stage work item: reserve exploration,
bound revisit age and job age, spend more confirmations on uncertain targets,
and keep skipped work unknown. Saved DS5 cannot evaluate unrecorded alternative
retunes. No firmware, production pipeline, public schema or scientific golden
fixture was changed.
