# Asymmetric offers for eight measured beacon sites

Anonymous Doppler selected the correct tile on **24/24** containing boards. A geometry-only chooser selected it on **19/24** using the shared coarse Illinois prior. The Doppler estimator localized better within the board, with **3.77 km** median forced error versus **12.18 km** for the geometry-only tile center. A reliable publication rule did not follow from that improvement. The added held time-shift check changed zero interior-only decisions, retaining **11/24** containing publications and **5/24** false publications on near omissions. The older full held gate withheld all containing queries and published one false fix at **5.79 km**. [Position chart](charts/c0/asymmetric-measured-site-offers.png) · [Per-query data](scores.csv)

| Policy | Containing publications | Containing published median | Omitted false publications | Omitted published median |
|---|---:|---:|---:|---:|
| Interior and held time-shift gain | 11/24 | 4.08 km | 5/24 | 10.45 km |
| Same fit with 1 km interior only | 11/24 | 4.08 km | 5/24 | 10.45 km |
| Older full held gate | 0/24 | — | 1/24 | 5.79 km |
| Geometry-only nearest offered center | 24/24 | 12.18 km | 24/24 | 16.80 km |

Six containing boards published within 5 km under the new gate, across five physical sites. Fourteen of 24 forced Doppler estimates were within 5 km and 20/24 improved on the same board's prior-only center. Across the four older held physical sites, the new policy published seven of twelve containing queries and falsely published on three of twelve near omissions. Its five false fixes across all eight sites occurred at three physical sites, with errors of 5.79–13.05 km. The three boards of each status per site share the same measured traces. [Case-level publication and forced results](scores.csv)

The held capped frequency RMS was **224.5 Hz** median on containing offers and **188.0 Hz** on near omissions, computed over all actual fits. Repeating the search and held evaluation after shifting the complete measured arcs yielded **841.2 Hz** and **848.5 Hz**, respectively. The time control showed that the signed measured evolution carried information in both conditions. It failed to establish offer validity. Every containing estimate failed the older full gate's requirement for a held advantage over a spatial rival. Fitted `c` is unavailable because the per-arc level absorbs its RF column exactly at one nominal RF. [Calibration availability chart](charts/fitted_c/asymmetric-measured-site-offers.png)

## Geometry audit

The previous site-relative construction could expose a midpoint. This test generated all four centers from a shared lattice around **40° N, 88° W**, with fresh phase, center jitter and ordering per board. The custody process used the GNSS point only after each draw to classify and enroll three containing and three near-omission boards per site. An omission meant the point was outside every offered square and 0.75–3 km from the nearest one. No measured outcome informed enrollment. The worker saw one board at a time, without the stream ordinal, GNSS or condition. The outcome still depends on the explicit coarse Illinois prior and on eligibility conditioning. [Frozen protocol](PROTOCOL.md) · [Geometry stream commitments](geometry-streams.json)

| Geometry-only estimate | Correct tile on containing boards | Median error, containing | Median error, omitted |
|---|---:|---:|---:|
| Common coarse anchor | — | 23.06 km | 23.06 km |
| Offer center nearest that anchor | 19/24 | 12.18 km | 16.80 km |
| First randomly ordered center | 4/24 | 82.62 km | 69.00 km |
| Arithmetic board midpoint | — | 34.05 km | 42.24 km |
| Closest pair midpoint, evaluator oracle | — | 18.81 km | 17.12 km |

The geometry-only nearest-center comparator saw only the four tile centers and the coarse regional anchor. It always issued an in-offer position. The board midpoint and pair oracle were audited as forced geometry diagnostics, outside the live receiver and the published decision chart. Neither landed within 5 km on any of the 48 boards. [Geometry audit data](geometry.csv)

## Scope and reproduction

These are eight previously studied physical locations near Urbana–Champaign, recorded by the same independent StarLoc system. This test starts at anonymous prepared 11.325 GHz beacon tracks with source-assisted window selection and source-reported causal orbital availability. The geometric holdout is new. The project has no new physical receiving installation or waveform transfer from this test. [Primary source](https://zenodo.org/records/19043854) · [Measurement and clock authority](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

All 48 isolated one-thread numerical requests completed under 35 s. Worker wall median was 3.96 s and numerical process CPU median was 2.65 s, including the actual time-shift refit. The numerical policies share one solve. [Sealed inputs](input-lock.json) · [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [Both standard charts](charts/index.html)

Stage the existing authenticated MAT files by capture directory and copy this protocol to a fresh output directory. The [base packets](base-packets.jsonl.gz) and [request manifest](requests.json) permit a direct numerical replay from sealed input. An initial post-prediction scorer passed NumPy midpoint arrays to an interface that accepts coordinate lists. The scorer now converts those arrays before distance measurement. The original prediction archive and [exact original runner](prediction-runner.py.gz) preserve the as-run source. The updated scorer and chart code are bound separately. [Scorer receipt](score-source.json)

```sh
study=tools.pipeline_eval.qualification.asymmetric_site_trial
python -m "$study" prepare "$WORK" --out "$OUTPUT" --raw "$STARLOC_MAT_ROOT"
nice -n 10 taskset -c 14,15 python -m "$study" predict "$WORK" --out "$OUTPUT"
python -m "$study" score "$WORK" --out "$OUTPUT"
python -m "$study" chart "$WORK" --out "$OUTPUT"
```
