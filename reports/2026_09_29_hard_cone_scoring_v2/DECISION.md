# Decision: hard nominal cones are not the next geographic model

The completed comparison rejects promotion of hard 40/50-degree gates at the
current fits. Hard40 loses held frequency score to both no-cone and soft40 in
all 18 panels. Hard50 loses to no-cone in 17/18 and to soft50 in 16/18. This
does not prove that no refitted hard model could improve location, but supplies
no predictive reason to prioritize that discontinuous optimization now.

The receiver geometry remains physically shared within every scan. A hard
boundary around an uncalibrated boresight is an additional assumption, not a
consequence of sharing geometry. Real antenna response, sidelobes, pose errors,
incomplete candidate banks and incorrect associations are still unresolved.

## Most predictive loss is not from completely unsupported tracks

The following decomposition uses the nine nonoverlapping eight-scan panels:
72 scans, 4,328 unique tracks. Values are changes relative to the unchanged
no-cone fit. More negative held score means worse prediction. Dataset totals
have different observation counts and must not be read as normalized rates.

| Dataset | Gate | Unsupported tracks | Held change, unsupported tracks (nats) | Held change, tracks with an in-cone candidate (nats) | Baseline signal → background tracks |
|---|---|---:|---:|---:|---:|
| DS7 | hard40 | 3 | −127.618 | −956.595 | 63 |
| DS8 | hard40 | 2 | −19.807 | −1,669.219 | 93 |
| DS9 | hard40 | 7 | −55.466 | −2,375.832 | 130 |
| DS7 | hard50 | 0 | 0 | −58.738 | 10 |
| DS8 | hard50 | 0 | 0 | −64.690 | 12 |
| DS9 | hard50 | 0 | 0 | −184.815 | 24 |

Signal → background means training signal responsibility changes from >0.5
in the baseline to ≤0.5 under the gate. This is a model assignment, not an
observed non-satellite label. All tracks remain in the evaluation. Even when
an in-cone candidate exists, it need not explain the measured Doppler well.

Among tracks remaining signal-dominant in both models, hard40 changes the
dominant candidate in 40/1,306 DS7, 42/1,258 DS8 and 71/1,226 DS9 tracks.
Hard50 changes it in 15/1,359, 21/1,339 and 39/1,332 respectively. These
candidate changes are not independently verified identity corrections.

The two predeclared RX0 conflicts both become entirely background at hard40;
their held changes are −2.266 and −20.775 nats. Hard50 retains their signal
explanations with changes +0.009 and 0.000 nats. Those two cases are only a
small part of the overall hard40 degradation.

The fixed positions differ from the earlier original-fit cone audit, so its
scan support counts should not be substituted here. At these q020 positions,
hard40 has 12 unsupported tracks in 11 scans; hard50 has none. This is not a
contradiction of the whole-domain bound, which proves only two unavoidable
40-degree exclusions and does not certify the remaining scans feasible.

## Next modeling priority

Return to temporal error structure and track contamination together. The
completed comparison tested correlated residuals and the normalized trend
mixture separately; it did not test their combination as a normalized
frequency-contrast likelihood. The proposed next experiment is a 10-second
correlated contrast model with q=0.20, comparing no cone and the existing soft40
arm. This is a new hypothesis, not an expected improvement or a selected winner.

Use covariance D Σ Dᵀ for anchored frequency differences, where Σ is the
existing fixed temporal kernel scaled by 100² Hz². Marginalize a constant offset
as in the existing contrast model. Keep the background's documented trend
slope uncertainty and specify its covariance consistently before execution.
Require exact zero-correlation replay, positive covariance, derivative checks,
anchor invariance and normalized conditional held density. A covariance change
must not quietly change background normalization or use held observations to
fit the model.

Then use the same 18 panels, shared location and one timing per scan, existing
training-only initialization/selection and numerical audit gates. Report all
failures and late DS9, and keep location changes separate from predictive gains.
No setting may be chosen by exposed-reference error. This proposal has not been
implemented or evaluated in this report; its execution budget and complete
protocol must be frozen before fitting. No new RF collection is needed.

The larger objective remains unmet: reliable sub-km short-set or individual-scan
accuracy across DS7/DS8/DS9 has not been established. All geographic comparisons
still use one exposed, unsurveyed site. Full-dataset nominal sub-km results do
not establish calibrated spatial resolution.

[Stored-score decomposition](decomposition.json), [derivation script](diagnose.py),
[all panel scores and reassociation denominators](summary.json),
[twenty-model comparison](../2026_09_29_cone_trend/MODEL-COMPARISON.md).
