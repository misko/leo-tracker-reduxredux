# An explicit outside option for measured beacon positioning

The outside-option gate published **6/16** containing fixes and **2/16** false fixes on near omissions. It rejected all **16/16** wider omissions. Compared with the 1 km interior-only rule, it withheld six extra valid offers and removed four false fixes, while introducing one new near-omission false fix. The original full gate withheld all 48 queries. At the four previously held sites, the outside option published two of eight valid offers and none of sixteen omissions.

| Decision policy | Containing publications | Near-omission false fixes | Wide-omission false fixes | Median published containing error |
|---|---:|---:|---:|---:|
| Inside versus exterior gate | 6/16 | 2/16 | 0/16 | 5.17 km |
| Original full held gate | 0/16 | 0/16 | 0/16 | — |
| Same fit with 1 km interior only | 12/16 | 5/16 | 0/16 | 3.41 km |
| Geometry-only nearest offered center | 16/16 | 16/16 | 16/16 | 7.81 km |

The two near-omission false fixes were 2.63 and 7.40 km from their receivers at two earlier development sites. The smaller error came from the newly introduced false fix. The other false fix also passed the interior check. Three of 16 containing queries published within 5 km, compared with eight for interior only. On the earlier held sites, interior only published on seven of eight containing queries and falsely published on two of sixteen omissions. These are repeated board outcomes over eight physical sites.

| Earlier site split | Outside gate, containing / near false / wide false | Interior only, containing / near false / wide false |
|---|---:|---:|
| Four development sites | 4/8 / 2/8 / 0/8 | 5/8 / 3/8 / 0/8 |
| Four held sites | 2/8 / 0/8 / 0/8 | 7/8 / 2/8 / 0/8 |

| Offered geometry | Exterior preferred in training | Median inside / exterior held RMS | Median inside / exterior / unrestricted forced error |
|---|---:|---:|---:|
| Contains receiver | 4/16 | 228.3 / 267.0 Hz | 4.01 / 9.22 / 6.07 km |
| Near omission | 8/16 | 188.1 / 188.9 Hz | 3.32 / 2.36 / 3.32 km |
| Wide omission | 16/16 | 396.9 / 212.2 Hz | 16.69 / 5.14 / 5.14 km |

The outside hypothesis identified wide omissions and substantially improved their forced estimates. Both hypotheses fit near omissions well, and the held RMS distributions still overlapped. Every run completed its 49 coarse probes per tile in each branch. The median additional wall time and CPU of the exterior branch were **1.06 s** and **1.02 s**. Total isolated worker wall time was **4.67 s** median, including the original time-shift refit for its matched full-gate control. A separate isolated run of the unchanged original solver matched the full-gate result and frequency diagnostics exactly on the first opaque request. [Stock parity receipt](stock-parity.json)

The same observation and causal orbit bytes feed the inside search and the new exterior branch. Each branch selects position, satellite identities and common receiver drift on early samples. It evaluates those choices on disjoint late samples. The new rule publishes only when training prefers inside, late data favor inside by more than one existing Fourier bin squared, and enough independent arcs support the inside trajectory. The [publication chart](charts/c0/field-outside-option-publication.png) and [forced-position chart](charts/c0/field-outside-option-forced.png) separate the publication decision from numerical estimates across both sampled regions. [Per-query decisions](scores.csv) · [Hypothesis and runtime data](hypotheses.csv)

## Measurement and geometry

The trial enrolls two containing, two near-omission and two wide-omission boards at each of eight previously measured StarLoc locations. It uses prepared 11.325 GHz beacon traces from the same traveling receiver installation. The custodian used GNSS only to classify a new independent stochastic stream of four-tile boards around a common coarse Illinois prior. Every isolated worker received only one board, measured Doppler and the sealed historical catalogue. Earlier results on these physical sites were known. The new offer placements were held out, and the report separately treats the four earlier development sites and four earlier held sites. [Prespecified protocol](PROTOCOL.md) · [StarLoc data release](https://zenodo.org/records/19043854) · [Field measurement authority](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

The exterior branch reaches up to 25 km beyond the offered union. Each tile supplies 49 coarse probes per branch and the same refinement step sizes. The exterior branch covers more area at lower spatial sampling density. Exterior probes inside any offered square are removed. This asks whether the receiver can find a stronger competing explanation near its offered tiles. The unrestricted diagnostic selects from the sampled inside and exterior hypotheses. The geometry-only control always chooses a legal offered center using the common coarse prior. Geographic error and held frequency-fit quality are scored separately.

At one nominal carrier, the per-arc intercepts exactly absorb the fitted RF term. The fitted-c arm is unavailable. These results begin with prepared measured beacon traces and the source's existing window selection. Capture-time availability of the causal catalogue is documented by the publisher. The experiment adds no raw waveform, independent hardware or newly measured location. [Calibration availability](charts/fitted_c/field-outside-option-publication.png)

## Reproduce

From the authenticated local StarLoc MAT release, copy [PROTOCOL.md](PROTOCOL.md) to a fresh output directory. The exact reconstructed inputs are archived as [base packets](base-packets.jsonl.gz) and a [board manifest](requests.json). The [draw stream receipt](draw-streams.json) records the deterministic enrollment streams. Follow the same command sequence with an unused work directory.

```sh
study=tools.pipeline_eval.qualification.outside_option_field_trial
python -m "$study" prepare "$WORK" --out "$OUTPUT" --raw "$STARLOC_MAT_ROOT"
nice -n 10 taskset -c 14,15 python -m "$study" predict "$WORK" --out "$OUTPUT"
python -m "$study" score "$WORK" --out "$OUTPUT"
python -m "$study" chart "$WORK" --out "$OUTPUT"
```

[Input lock](input-lock.json) · [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [Chart index](charts/index.html)
