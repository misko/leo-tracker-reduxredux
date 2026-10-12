# Continuous track merging study

Continuous curves describe the two investigated track pairs without a separate frequency offset or drift for either half. The prototype also rejects injected frequency steps and slope changes that a residual RMS limit alone accepts. Improvement in localization remains under evaluation.

The pinned study includes all 18 original DS20 recordings and all 63 DS16 recordings. DS15 is awaiting an authoritative manifest and is not replaced by another corpus. The implementation is an explicit offline bootstrap intervention; automatic tracking and localization defaults are unchanged.

## Measured trajectories

Colored points are original passing GLRT CFO candidates assigned to the investigated segments. Black curves span both segments; purple dashed curves fit each separately. Frequencies are aligned by known integer pilot aliases and normalized to 11.2 GHz. Shaded intervals contain no retained measurement, so continuity there is a prediction.

![Measured GLRT CFO and joined curves](glrt-and-curves.png)

T9 and T16 on CH6 RX1 require a fourth-order curve to remove the systematic residual structure left by a cubic. T19 and T26 on CH3 RX0 are adequately described by one cubic. These examples support continuous trajectory proposals; they do not establish satellite identity.

## Joining algorithm

The implementation considers consecutive segments on the same channel, edge, receiver, and actual RF tuning, with a gap of at most eight seconds. Overlap of up to 50 ms permits a shared boundary probe; the union retains one existing candidate per probe. Different RF lanes retain the existing grouping behavior.

Local quadratic extrapolation selects an integer pilot alias, without a freely fitted frequency shift. Boundary predictions must agree within 2,500 Hz. A single joint polynomial of degree two, three, or four is then fitted. Reproducible five-fold partitions hold out whole two-second capture-time blocks, with eight repetitions and seed 20261012. Curve coefficients are fitted only on training observations. The least flexible curve within ten percent plus five hertz of the best predictive RMS is selected.

The residual audit compares that continuous curve with a model that additionally permits a frequency step and slope change at the boundary. Provisional checks require:

| Check | Limit |
|---|---|
| Median held-out RMS | 500 Hz |
| Boundary step | Larger of 200 Hz and twice fitted RMS |
| Boundary slope change | Larger of 20 Hz/s and twice fitted RMS divided by the shorter segment span |
| Predictive improvement with a step and slope change | Larger of 20 Hz and twenty percent of continuous held-out RMS |
| Mean residual in either segment | Larger of 100 Hz and fitted RMS |
| Quadratic residual trend range in either segment | Larger of 100 Hz and twice fitted RMS |

These are development choices, not established false-join guarantees. Every later union rechecks the whole combined trajectory, so a chain of individually acceptable pairs cannot bypass the tests.

The application adapter changes bootstrap proposals while preserving the original observation object, candidate IDs, CFO, RF frequencies, device timing, and window membership. It retains the existing requirement of 15 observations over 15 seconds and the longest-12-per-receiver quota.

## Boundary checks detect faults that RMS alone misses

| Pair and perturbation | Continuous held-out RMS | Checks enabled | Checks disabled |
|---|---:|---|---|
| T9 and T16 original | 30.4 Hz | Accept | Accept |
| T9 and T16 plus 2 kHz step | 467.5 Hz | Reject | Accept |
| T9 and T16 plus 100 Hz/s slope change | 56.8 Hz | Reject | Accept |
| T19 and T26 original | 95.6 Hz | Accept | Accept |
| T19 and T26 plus 2 kHz step | 405.3 Hz | Reject | Accept |
| T19 and T26 plus 100 Hz/s slope change | 114.8 Hz | Reject | Accept |

The earlier plots selected these pairs before this study. Their block tests are conditional development evidence rather than independent validation. The injected controls validate these particular perturbations and amplitudes; smaller faults and unrelated satellites need broader testing. Receipts are in [anchor-results.json](anchor-results.json).

## Corpus evaluation

[membership.json](membership.json) pins the original DS20 and DS16 authorities and records a random whole-recording split: one third of each dataset is assigned to validation using seed 20261012 and NumPy PCG64. Membership does not depend on readiness or accuracy. Missing and failed analyses remain explicit. Both corpora were examined in earlier investigations, so these are exposed-data comparisons rather than untouched validation.

One DS20 member lacks a published tracking input in the original manifest. The study uses its previously sealed recovery input, preserving original counters and recorded clipping omissions. Original DS20 membership remains unchanged. Large derived inputs and checkpoints stay in Git-ignored `local/` storage.

The first census batch completed eight DS20 and eight DS16 recordings with no preparation failures. It selected 77 joins in DS20 and 40 in DS16, changing the selected bootstrap proposals in all 16 recordings. These are proposal counts, not additional satellites or localization improvements.

![Selected joins in the initial census batch](initial-census.png)

Full default B7 replays compare no merging, replacement with guarded joins, retention of original segments alongside guarded joins, and joins with residual guards disabled. Conditions share original observations, initial satellite bank, prior, and the default 400-point search budget. Final satellite sets and calibration may change as consequences of the intervention.

Each condition includes `c = 0` and fitted-`c` arms. The two arms share fitted-`c` upstream conditioning and the final candidate set within that condition, matching the deployed pipeline's conditional ablation. This does not refit discovery with `c = 0`. Frequency likelihood and score changes will be reported separately from horizontal position error. Reference coordinates enter evaluation only after numerical results are recorded.

## Reproduction and remaining evaluations

Nine new component tests cover alias alignment, discontinuity rejection, gap and lane limits, deterministic unions, observation preservation, and the append ablation. Three existing position-input tests verify baseline behavior. No new RF collection is required.

The tools are [continuous_merge_study.py](../../tools/continuous_merge_study.py) and [continuous_merge_positions.py](../../tools/continuous_merge_positions.py). Use a NumPy/SciPy environment, `PYTHONPATH=src:tools`, and one BLAS thread. Build the existing native orbit extension before positioning:

```bash
python setup.py build_ext --inplace
python tools/continuous_merge_study.py mint
python tools/continuous_merge_study.py census --limit 16 --maximum-seconds 420
python tools/continuous_merge_positions.py freeze DS20 SESSION_ID
mkdir -p reports/2026_10_12_continuous_track_merge/local/DS20/SESSION_ID/positions/baseline
python tools/continuous_merge_positions.py execute DS20 SESSION_ID --variant baseline --maximum-seconds 420
```

The checkpoint adapter requires the variant output root to exist. Repeating `execute` resumes verified stages after a yielded worker slice. `mint` freezes membership and source hashes and refuses to overwrite an existing study. Local authority paths identify input artifacts; reference repositories are not runtime dependencies.

The census and first matched positioning replays are in progress. Remaining evaluations cover the full DS20 and DS16 populations, DS15 after its authority is located, accuracy and failure rates for each condition, regressions, and sensitivity to curve flexibility, residual limits, and gap length. The current evidence does not yet establish a localization improvement or justify enabling automatic merging.
