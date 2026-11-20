# False fixes on new geographic offers for eight measured sites

The unchanged anonymous Doppler receiver withheld all 24 omitted-region queries and all eight containing queries. The same numerical fit with only its existing 1 km interior check published on all eight containing boards and falsely published on **two of eight near-face omissions**. It withheld every corner and far omission. Ungated publication produced a false fix on every omission. [Position chart](charts/c0/independent-site-omission-frontier.png) · [Fitted-c availability](charts/fitted_c/independent-site-omission-frontier.png) · [Per-site results](scores.csv)

| Four-tile offer | Held gate publications | Interior-only publications | Ungated publications | Median forced error | Median held robust frequency RMS |
|---|---:|---:|---:|---:|---:|
| Contains receiver | 0/8 | 8/8 | 8/8 | 4.07 km | 224 Hz |
| Receiver 1 km beyond a face | 0/8 | 2/8 false | 8/8 false | 3.40 km | 154 Hz |
| Receiver 1 km beyond both corner axes | 0/8 | 0/8 | 8/8 false | 1.80 km | 161 Hz |
| Receiver 20 km beyond a face | 0/8 | 0/8 | 8/8 false | 20.64 km | 487 Hz |

The two interior-only false fixes were **6.29 km** and **8.05 km** from their measured receivers, with 2 km and 1 km of tile slack. Both came from site groups 01–04, the development sites in the older study. The new geometry was held out at all eight sites. On site groups 05–08, the interior-only check published all four containing fixes and withheld all twelve omissions. Each per-condition denominator is eight physical site groups. The 24 omitted queries share observations in groups of three.

Five of eight containing estimates fell within 5 km. Each full held gate failure on a containing board had an inadequate held advantage over a tested point at least 5 km away. Held carrier fit was better on the wrong board than the matching containing board at four of eight near-face cases and six of eight corner cases. The near-omission controls show that a small forced error or an improved carrier fit can occur on a geographically invalid offer. The forced point, frequency score and orbit evidence are identical across the three decision policies for each query. [Original four-region receiver and earlier data split](../../acquisition-support/field-anonymous/README.md)

The bounded source check found no additional receiving installation with verified location, time-referenced signed Doppler and causal orbital support. The fallback uses newly generated tile placements on eight previously documented physical locations recorded by the same independent StarLoc hardware. All measured inputs are anonymous prepared Ku beacon Doppler at 11.325 GHz. Published GNSS logs supply location truth. Source-selected tracking windows and source-reported causal catalogue availability limit interpretation. The per-arc intercept absorbs the RF calibration term at one nominal carrier, giving `c` exact projected rank zero. The fitted-c arm records unavailable. [Source review](source-check.md) · [Primary release](https://zenodo.org/records/19043854) · [Measurement provenance](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

Each query used a separate, single-threaded CPU 6 process. Median worker wall time was 2.35 s and median numerical CPU time was 1.58 s. All 32 jobs completed, with wall times of 1.48–4.77 s under the frozen 35 s cap. The comparison reuses one fit per board, including the shifted-time solve. The timing covers its actual propagation and position search and excludes initial data staging and evaluation. [Sealed input](input-lock.json) · [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json)

## Reproduce

Stage the locally authenticated StarLoc `tracked_tones.mat` files by capture directory and copy [PROTOCOL.md](PROTOCOL.md) to an unused report output folder. The worker input bundle is also available for replay without the source MAT files. [Receiver requests](requests.jsonl.gz)

```sh
study=tools.pipeline_eval.qualification.independent_site_omissions
python -m "$study" prepare "$WORK" --raw "$STARLOC_MAT_ROOT" --out "$OUTPUT"
nice -n 10 taskset -c 6 python -m "$study" predict "$WORK" --out "$OUTPUT"
python -m "$study" score "$WORK" --out "$OUTPUT"
python -m "$study" chart "$WORK" --out "$OUTPUT"
```
