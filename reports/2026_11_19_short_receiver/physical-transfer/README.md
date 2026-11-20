# Receiver transfer to independently measured sites

The searched collections supplied no local Qin-pilot IQ or compatible native GLRT from an independently located installation with both a causal catalogue and a released receiver coordinate. They did supply four independent StarLoc sites for a fresh fit from prepared anonymous beacon tracks. That fit **published one worldwide position 9,471 km from GNSS** and withheld the other three. Supplying the correct tile reduced median forced error to 3.53 km, versus 6.95 km for the tile center alone. The receiver withheld all four supplied-correct and all four omitted-tile decisions. [Protocol](PROTOCOL.md) · [Sealed positions](positions.jsonl.gz) · [Scored site results](scores.json)

## What exists on disk

| Collection | Verified signal boundary | Consequence for the current raw receiver |
|---|---|---|
| StarLoc local staging | Eleven MATLAB tone files, eleven TLE files and 88 GNSS log fragments. The MATLAB directories expose `tones_dict`, `main_tone_dict` and `id_dict`. Zero `inrx*.dat` members were found in the staged source. | The separately released IQ is specified as 2 MS/s around 11.325 GHz. The channel-3 Qin lower and upper centers are 11.2096875 and 11.4403125 GHz, each 115.3125 MHz from the beacon center. The recorded band omits both. The prepared test uses only measured time and baseband Hz. |
| Altrincham local staging | Three evaluation hours plus a preflight hour. Each retained CSV contains 3,600 rows and 1,024 distinct powers spanning 1 MHz. The retained evaluation files generated zero accepted tracks. The prior-night TLE is present. | Power integration discards complex phase and sample timing. The spectra cannot reconstruct the complex samples or native probe GLRT. |
| Older named QNAP field archive | One named site, with 50 manifests at 1.2 or 4 MS/s. Its documented site is within 14 m of both roof benchmark references. The field report withheld a positive Starlink identification on these sweeps. | This is nearby capture evidence with uncertain signal identity. It does not establish independent site transfer. |
| UT exemplar collection | A 5.42 GB MATLAB v7.3 file of 1,009 decoded and corrected OFDM frames with derived time-of-arrival and Doppler metadata. | Its frame arrays begin after synchronization and demodulation. They lack the original continuous IQ or preselected native candidate alternatives needed for a comparable receiver replay. |

The public passive-detection collection documents a single 100 ms complex IQ snippet alongside detection statistics and power envelopes. The bounded local search found no copy of that snippet and no verified independent acquisition cohort connecting it to both released truth and a causal catalogue. The Direct-to-Cell collection could not be verified on disk. The retained Heinl MAT annex is a frequency extract whose released selection enables `IDENTIFY_AT_TRUTH`. [Disk audit and source hashes](raw-source-audit.json) · [StarLoc raw specification](https://zenodo.org/records/19043854/files/starloc_full_dataset_README.md?download=1) · [Altrincham release](https://zenodo.org/records/8400658) · [Passive collection file inventory](https://github.com/lukepwilson/starlink-passive-detection#repository-layout) · [Heinl source audit](../../2026_11_18_blind_regional_receiver/field2_private/provenance.md)

## Fresh prepared-track evaluation

The stager used the first chronological capture in each of the final four distinct StarLoc site groups, `05` through `08`. The four captures supplied 7, 11, 4 and 7 tracks respectively and 5,675 retained causal element sets per capture. The original StarLoc documentation places TLE retrieval at capture start. The local preparation discards element epochs after the recorded cutoff. Retrieval time is author-reported. [Original field and catalogue provenance](../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

Each worker ran in a fresh process and network namespace. The worldwide packet contained an opaque alias, original measured track ordinates and times, RF, and causal TLE text. The two bounded modes each received one declared center. The routing controller used group and offer labels only. It kept the raw MATLAB satellite labels, prior predictions and GNSS coordinates out of the worker. The scorer attached reference coordinates after verifying the prediction lock. The four sites were held out from parameter fitting. This is a new blinded execution on a previously released cohort. [Alias and source plan](plan.json) · [Prediction lock](prediction-lock.json)

The model assigned each anonymous track to one propagated orbit at a trial site and estimated a constant offset on the first six of nine sampled measurements. The final three checked that assignment and offset. A fixed-RF calibration term is absorbed exactly by the fitted constant, so both calibration arms produced identical results. The 0.08 held lead gate admitted site `05`'s wrong worldwide solution with six supported orbit assignments, 619 Hz held RF RMS and a 0.092 held lead. The within-track holdout can therefore agree with multiple geographically unrelated satellite explanations.

| Site group | Worldwide forced km | Correct tile forced km | Correct center km | Omitted tile forced km |
|---|---:|---:|---:|---:|
| `05` | 9,471.06, published | 2.63 | 6.08 | 74.29 |
| `06` | 2,252.28 | 2.64 | 8.07 | 32.36 |
| `07` | 7,587.26 | 9.74 | 7.82 | 139.85 |
| `08` | 6,073.45 | 4.42 | 2.82 | 83.05 |

The correct-tile forced coordinate improved on the supplied center on two of four sites. All omitted-tile runs withheld. Wall time including sandbox startup and packet decoding was 6.93–19.32 s worldwide, 1.50–2.95 s with the correct tile and 1.49–3.09 s with an omitted tile. These times start at prepared-track input and exclude beacon extraction. The score field `false_publication` counts publications specifically in the omitted-tile policy. The erroneous worldwide publication is preserved separately with its measured geographic error. [Full comparison](scores.json)

## Reproduce

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 10,11 .venv/bin/python -B -m tools.pipeline_eval.qualification.physical_transfer \
  predict --out "$NEW_OUTPUT_DIRECTORY"
.venv/bin/python -B -m tools.pipeline_eval.qualification.physical_transfer \
  score --out "$NEW_OUTPUT_DIRECTORY"
```
