# Late validation of frozen anonymous beacon pairs

The receiver withheld all 33 decisions on eleven measured StarLoc captures at eight locations. In the two strongest primary captures, carrying early orbit identities and pair offsets forward made the real late blocks fit substantially better than the same blocks shuffled. A different orbit assignment at the same point and a spatial rival at least 6 km away still fit those real blocks better. The results establish sensitivity to temporal order and leave geographic and identity ambiguity unresolved. [Protocol](PROTOCOL.md) · [Sealed predictions](prediction-lock.json) · [Matched scores](scores.json)

## What transfers from the early measurements

The input is measured simultaneous beacon frequency at one nominal RF. Exact differences cancel a common receiver-frequency term. The released track builder can assign different beacon carrier levels, so the fit estimates one constant per paired track difference. For each orbit map and point, the early samples set that constant. The late comparisons hold the point, the complete ordered pairing and the fitted constants fixed. The earlier anonymous coincidence study centered the late data separately. Here the held data also challenge the early winner against retained rival orbit maps at the same point and retained maps at least 6 km away. The retained set is six early pair candidates per pair after early per-side shortlisting. This is a bounded competitor set. [Prior exact-coincidence study](../../inference/physical-differences/README.md)

The isolated worker sees an anonymous request ID, one unnamed 25 km offer, measured time and Hz, and the frozen causal TLE. There are no author satellite labels or GNSS inputs to the receiver. The controller chooses the previously declared offers and the scorer joins GNSS after the prediction seal. The late control permutes the last third of both observed curves together. All eleven pairs of requests share their exact early payload digest, and all seven that furnished predictions produce the same early orbit map, fitted levels and point before and after the permutation. A common fitted `c` cancels algebraically at this RF, so the two arms are identical. The same instrument moved between the eight measured locations. [Field provenance](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md) · [Input bindings](plan.json)

## Primary and repeated results

| Cohort and offer | Attempts | Published | Forced | Median forced error | Earlier exact-pair median on this roster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary, containing | 8 | 0 | 5 | 6.91 km | 6.91 km |
| Primary, omitted | 8 | 0 | 5 | 115.02 km | 115.02 km |
| Primary, late shuffle | 8 | 0 | 5 | 6.91 km | — |
| Repeat, containing | 3 | 0 | 2 | 11.85 km | — |
| Repeat, omitted | 3 | 0 | 2 | 52.17 km | — |
| Repeat, late shuffle | 3 | 0 | 2 | 11.85 km | — |

The earlier method and this receiver had the same no-fix decision on all 16 matched primary unshuffled offers. Eight of the ten numeric forced errors are identical. At site 03 the new joint early fit moved the containing forced error from 1.70 to 4.90 km. Its omitted forced error moved from 277.66 to 277.49 km. The same five containing offers have an 8.79 km median tile-center error. The earlier offset-only receiver published zero positions on the four common primary sites 05–08. Where both fit a point, the earlier containing errors were 2.64 and 4.42 km at sites 06 and 08. The new errors were 5.30 and 6.91 km. For their omitted offers the same comparison is 32.36 and 83.05 km versus 41.86 and 104.55 km. [Prior offset-only matched results](../../../2026_11_19_short_receiver/physical-transfer/scores.json) · [`c = 0` position figure](position-errors-c0.png) · [Fitted `c` position figure](position-errors-fitted_c.png)

| Primary containing site with two disjoint pairs | Frozen late RMS | Late blocks shuffled | Best same-point rival | Best separated rival | First failing gate |
| --- | ---: | ---: | ---: | ---: | --- |
| 03 | 120.1 Hz | 382.7 Hz | 118.5 Hz | 106.3 Hz | Orbit identity lead |
| 04 | 985.8 Hz | 1,879.1 Hz | 217.4 Hz | 54.3 Hz | Paired forecast residual |
| 06 | 69.1 Hz | 310.9 Hz | 64.7 Hz | 45.8 Hz | Orbit identity lead |

The withheld identity margins for sites 03 and 06 were −391 and −588 Hz². Both lost on local identity even at a zero lead threshold. Their spatial margins were also negative. At site 06 the omitted offer gave 66.3 Hz frozen held RMS, slightly below the containing offer’s 69.1 Hz, while its forced point was 41.86 km from GNSS. The block control can distinguish ordering at this site without distinguishing receiver location. The previous supplied-identity study also separates region evidence from local conditioning and has a different input boundary. [Supplied-identity control](../../streamlined/measured-transfer/README.md)

The confirmation captures were the second site-02 acquisition `6Mar2024_04_19`, the site-03 acquisition `12Mar2024_23_35`, and the site-04 acquisition `13Mar2024_00_54`. Their eligible independent pair counts were 0, 1 and 1. Site 04’s repeat reached 298.8 Hz held RMS at a forced point 2.32 km from GNSS, but a separated point reached 145.0 Hz. The repeats are fresh time windows at known physical sites and offer sparse evidence with the same instrument.

The 33 isolated worker jobs completed in 14.6 s on CPUs 7 and 8. Worker wall time was 0.37–1.68 s, including namespace startup and geometry. This replay starts at the released measured tracks, after the sender’s beacon extraction.

## Reproduce

Copy the frozen protocol into an unused output directory. Use the local staged MAT directory and an existing bulk scratch directory.

```sh
cp reports/2026_11_19_receiver_screening/next/anonymous-transfer/PROTOCOL.md "$OUTPUT/"
nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  TMPDIR="$BULK_SCRATCH" taskset -c 7,8 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.anonymous_frozen_pairing predict \
  --raw "$STARLOC_MAT_ROOT" --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.anonymous_frozen_pairing \
  score --out "$OUTPUT"
```
