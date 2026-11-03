# DS23-0268: association recovery and a receiver-geometry audit

The retained causal prototype freshly reproduces **2,316 / 3,165 original winning GLRT observations associated (73.175%)**, in 64 graph tracks and 17 satellite labels. A new, more cautious control excludes the family requiring the largest sky-direction correction, refits from the regional centre, and still retains **2,226 / 3,165 (70.332%)**, in 61 tracks and 16 labels. Both controls pass the unchanged curved and predictive residual gates in both `c = 0` and fitted-`c` arms. No additional GLRT peak is included in either numerator.

These are model-compatible associations, not independently certified transmitter identities. This is single-scan development, not a production algorithm change or evidence of generalization. The frozen ALGO02 source verification still passes. No new RF collection was performed.

## What prevented association

The preceding [identity-resolution investigation](../2026_10_20_ds23_0268_identity_resolution/README.md) separates three mechanisms:

1. Receiver calibration covariance was too coarse for the intact RX1 CH7 curve near 150 seconds. A finer receiver basis, normalized to preserve average pointwise prior variance on the fixed scan grid, recovers its 60 points as causal 64333. This does not uniquely prove an instrumental cause: an independent-family transfer control has a retained-gate limitation.
2. An unconstrained objective optimum could fail an acceptance gate. Adding the 66797 curves made an existing slope statistic reach 3.021 against its limit of 3. Refining the same objective subject to the original gates, with a stricter 0.01 normalized interior margin, retains those curves and their frozen-calibration extension. No residual threshold was loosened.
3. Receiver calibration and satellite nominations were coupled. Updating only the RX1 curved nominations left related predictive fragments nominated to 53923. Coherently changing the RX1 curved and predictive nominations, followed by phase-refreshed constrained fitting, gives compatible alternatives. Predictive linear evidence does not update calibration.

| Retained stage | Original GLRT associated | Fraction | Position error c0 / fitted-c, km |
|---|---:|---:|---:|
| Receiver-step and family-reentry starting point | 2,111 | 66.70% | 5.359 / 5.485 |
| Finer receiver covariance; intact CH7 → 64333 | 2,171 | 68.59% | 5.216 / 5.273 |
| Recover 66797 with original gates | 2,254 | 71.22% | 3.867 / 3.636 |
| RX1 disputed family → 67953; RX2 → 53923 | 2,254 | 71.22% | 1.240 / 0.943 |
| Add intact RX1 CH2 curve → 67953 | 2,316 | 73.18% | 1.577 / 1.343 |
| New control: exclude largest sky-correction family, 69445 | 2,226 | 70.33% | 1.722 / 1.507 |

The first five rows summarize preserved earlier fits that were independently replayed. The last row is a new paired exclusion/refit in this review. Geographic truth enters only report-side error calculation; it is not used to select the excluded family, nominate satellites, fit position, or accept observations. Each c pair has matched masks, labels, priors and search budgets. RF bounds across different observation masks are not compared.

![All original GLRT observations and retained graph curves](../2026_10_20_ds23_0268_visibility_reentry/accepted_split_73percent_GLRT.png)

In this 73.18% figure, green denotes retained identity, purple the RX1 53923→67953 relabeling, blue the newly associated CH2 observations, and pink the 849 remaining unassociated observations. Of those 849, 470 are in graph tracks and 379 are outside every graph track. They remain unexplained evidence, not declared clutter.

## Was 53923 wrong?

**The evidence supports an identity ambiguity, not a claim that every original 53923 assignment was wrong.** All ten earlier 53923 graph tracks have one polynomial piece; a multi-piece graph join is not demonstrated as the cause. A single piece can still contain mixed or erroneous GLRT observations.

On the same 2,254 observations, changing the RX1 family to 67953 lowers the negative-twice RF variational bound by 41.260 / 40.122 in c0 / fitted-c. The whole disputed family assigned to 67953 also passes. Its bound is only 4.120 / 4.709 worse than the split. Those differences are not calibrated identity probabilities, and the geographic errors cannot choose an emitter identity.

A family-excluded search removes all 53923 curved and predictive evidence from calibration and position, then screens all 1,402 causal catalogue candidates. RX1 prefers 67953 and RX2 prefers 53923. However, that diagnostic calibration fit fails other retained gates and does not integrate calibration uncertainty into proposal scores. It exposes nomination/calibration feedback but cannot certify the split.

One existing simultaneous IQ window supports a common received component across receivers. A matched calibration-anchor control does not resolve the competing identities. Common pilot structure or a weaker shared emitter also remains possible. See the earlier report for the waveform controls and alias treatment.

In the 73.18% split, 53923 owns 268 points in six RX2 tracks; 67953 owns 162 points in five RX1 tracks. Their fitted phase corrections are approximately +0.918 s and −2.295 s. The whole-family alternative must remain explicit.

## Sky geometry: every association checked

The independent nominal audit directly propagates each causal TLE at each original observation timestamp, with zero fitted phase/orbit correction, at the RF-estimated position. All catalogue element epochs and collection timestamps precede the scan cutoff. The station record matches the recording radio and validity interval. A second audit reconstructs the fitted phase/orbit directions and checks the same unique observation IDs.

For the retained 73.18% model:

- All 2,316 observations in all 17 labels are above the nominal horizon; minimum elevation is 34.060° / 34.062° in c0 / fitted-c.
- No observation is behind its nominal feed axis. Maximum nominal off-axis angle is 48.062° / 48.048°.
- Fitted phase/orbit directions also remain above the horizon: minimum 34.061° / 34.057°, maximum off-axis 47.934° / 47.933°.
- Eight c0 observations and seven fitted-c observations exceed 45° off-axis. The 45° line is a sensitivity reference, not a measured beam boundary.

The nominal mount axes are RX1 west / RX2 east, each at 70° elevation for a level base, so the feed axes are only 40° apart. They do not observe disjoint sky hemispheres. Installed boresights, connector mapping, beam response, obstructions and phase centres are not fully measured. Observer altitude is assumed zero metres. **Horizon/front-axis consistency is verified; actual antenna visibility cannot be certified from the available metadata.**

![Every associated satellite, nominal and fitted geometry](all_satellite_geometry.png)

The following per-label summary uses the fitted-c RF position and **nominal causal TLEs**. Minimum elevation and maximum off-axis angle are over the actual associated observations on the listed receivers, not an entire orbital pass.

| NORAD | Receivers | Points | Minimum elevation | Maximum off-axis |
|---|---|---:|---:|---:|
| 53923 | RX2 | 268 | 60.00° | 35.47° |
| 54873 | RX2 | 42 | 61.41° | 14.61° |
| 59328 | RX2 | 42 | 59.50° | 14.33° |
| 60415 | RX1, RX2 | 177 | 58.91° | 36.69° |
| 61977 | RX1 | 125 | 48.90° | 35.47° |
| 63901 | RX1 | 91 | 45.42° | 48.05° |
| 63913 | RX1 | 85 | 50.86° | 46.79° |
| 64333 | RX1 | 60 | 51.18° | 27.81° |
| 64908 | RX1, RX2 | 267 | 39.17° | 42.20° |
| 64923 | RX1 | 306 | 42.58° | 27.78° |
| 64925 | RX1 | 206 | 43.09° | 26.92° |
| 66797 | RX1 | 83 | 34.06° | 36.21° |
| 66812 | RX1 | 31 | 40.98° | 29.02° |
| 67935 | RX1, RX2 | 122 | 38.44° | 37.29° |
| 67953 | RX1 | 162 | 62.09° | 41.86° |
| 68343 | RX1 | 159 | 44.45° | 38.81° |
| 69445 | RX1, RX2 | 90 | 40.26° | 45.46° |

## New diagnostic: the largest fitted sky correction

The geometry reconstruction flags **69445**, independently of geographic error: its +12.594 s fitted phase changes sky direction by as much as 10.808°. Almost all that change comes from phase; the additional linear orbit modes change direction by at most 0.0039°. Its causal TLE epoch is 20.48 hours before the scan. A large phase correction is not proof of a wrong identity, but it warrants separating its evidence from the headline coverage claim.

Exclude all of that family's curved and predictive factors and forbid counting its extension tracks. Retain the original remaining nominations, aliases, powers, receiver covariance and physical priors. Refit each c arm from the centre of the same 25 × 25 km regional box for five phase rounds with up to 48 position steps per round, then five constrained rounds of at most 40 steps with the same stricter 0.01 interior margin. No reference coordinate or future TLE enters this experiment.

Both arms pass. All **2,226 other previously associated observations** survive, with zero losses among those observations; only the 90 observations in the excluded family's three tracks are removed. Fresh independent reconstruction reproduces the objective, original gates and membership. The remaining 16 nominal satellite labels are all above the horizon: minimum 34.075° / 34.080°, maximum nominal off-axis 48.093° / 48.084°.

![Association coverage and geographic error with the large-phase family excluded](phase_exclusion_comparison.png)

Removing 69445 slightly worsens geographic error, from 1.577 / 1.343 km to 1.722 / 1.507 km. The control demonstrates that the 70% association target does not rely on that large-phase family. It does **not** establish a general family-deletion rule or show that exclusion improves localization. The other 16 identities are still model hypotheses.

## Recommendation and reproducibility

Report 73.18% as model-compatible coverage, alongside the 70.33% control with the largest phase-displacement family excluded. Retain the competing 53923/67953 identities. Do not turn nominal antenna angles into hard vetoes without a measured response. A more discriminating next observation would be repeated, uncertainty-qualified differential receiver measurements at multiple epochs; one shared-component window cannot establish all transmitter labels. This recommendation does not request or start new RF collection.

Use `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` with `.venv/bin/python`:

1. `tools/verify_ds23_0268_selected_result.py --proposal selected_split_all_RX1_with_CH2_constrained` independently replays the retained prototype.
2. `tools/review_ds23_0268_geometry.py` reconstructs all nominal/fitted direction comparisons and per-family tables.
3. `tools/probe_ds23_0268_phase_sensitivity.py --stage run` performs the paired exclusion/refit; it refuses to overwrite existing trials. `--stage verify` independently checks their original gates, ownership and direct nominal propagation.
4. `tools/report_ds23_0268_phase_sensitivity.py` computes report-only position errors and the paired control figure.

Focused geometry, family-exclusion, identity, calibration, event and ownership tests pass (16 tests). Frozen ALGO02 source verification passes. All new numerical jobs are terminal; no production algorithm was changed.

[Per-satellite/receiver table](per_satellite_receiver.csv) · [Per-observation nominal/fitted audit](per_observation.csv) · [Retained geometry receipt](audit.json) · [Exclusion independent replay](phase_exclusion_independent_audit.json) · [Exclusion nominal sky ledger](phase_exclusion_nominal_sky.csv) · [Matched c-arm comparison](phase_exclusion_comparison.csv)
