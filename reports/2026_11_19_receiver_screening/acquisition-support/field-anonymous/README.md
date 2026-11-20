# Blind field positioning with one shared receiver drift

The new receiver withheld all 33 decisions from eleven measured StarLoc captures. Among four offered tiles containing the receiver's tile, the forced result chose the correct tile on **all four held sites** and landed within 5 km on **three of four**. A tested point at least 5 km away fit the late measurements better at every held site. With a fixed worldwide search that used no supplied site region, the median forced error was **6,170 km** and scrambled timing fit better at all four held sites. [Held-site figure, `c = 0`](charts/c0/field_anonymous_doppler_holdout.png) · [Held-site figure, fitted `c`](charts/fitted_c/field_anonymous_doppler_holdout.png) · [Raw scores](scores.json)

## Measured receiver boundary

The packets contain 4–11 anonymous measured FFT-beacon arcs per capture at one nominal 11.325 GHz RF. The worker receives measured time and baseband frequency, the causal orbit text, and either no geography or all four regional centers. Each request runs in a separate namespace. The author-supplied satellite identifiers, GNSS, altitude, phase and orientation stay outside the worker. The measured arc windows come from the released signal processing, whose window-selection provenance is undocumented. This measures transfer of a receiver operating on prepared tracks. The eight site groups use one instrument in a geographical area about 15 km across. Sites 01–04 and their repeat captures form the development cohort. Sites 05–08 form the holdout. The replay froze both sets of decisions before running and uses a previously released field panel. [Protocol](PROTOCOL.md) · [Field source, clock and catalogue authority](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md) · [Source, per-record input and compiler receipts](source-lock.json)

At each trial position, the fit removes one constant per arc and profiles one common affine receiver-frequency drift across all arcs. This links anonymous tracks even when their passes do not overlap. The first eight thinned samples set the orbit identity, carrier level, drift and point. The last four compare the resulting forecast with rivals. The physical negative translates each entire observed arc by 225 seconds in a direction that leaves it inside the capture, then repeats the same candidate search. This preserves within-arc frequency evolution and intervals and changes their relation to the causal satellite trajectories. The degree lattice for the worldwide arm applies equally at every capture. Its coarse starts and finite refinement budget can miss narrow geographic basins. The other two modes reuse the earlier full four-tile offers and therefore receive geographic information through the historical evaluator placement. A constant `c` at one RF is absorbed by the per-arc levels, giving identical arms.

## Held geographic and frequency outcomes

| Held offer | Publications | Median forced error | Earlier grid, forced median | Median held RMS | Shifted-time RMS | Worker wall / numerical CPU, median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed worldwide lattice | 0/4 | 6,170 km | — | 753 Hz | 642 Hz | 6.31 / 5.70 s |
| Four offers, receiver included | 0/4 | 3.37 km | 4.04 km | 220 Hz | 767 Hz | 2.30 / 1.56 s |
| Four offers, receiver omitted | 0/4 | 42.73 km | 34.11 km | 745 Hz | 681 Hz | 2.04 / 1.54 s |

The RMS in the table is the square root of the clipped mean squared held loss across all arcs. In the containing offers, the forecasts beat the independently refit shift control and the best held alternative in another tile on 4/4. All four early winners lost to a local held rival. Site 06’s forced coordinate landed 0.50 km from GNSS, with 153 Hz held RMS against 765 Hz for the time shift. A point at least 5 km from that early winner reduced held loss by 1,804 Hz². Site 07’s forced point was 10.94 km from GNSS despite an even larger lead over the other offered tiles. Its forced error exceeded both the selected tile center’s 7.82 km and the earlier grid’s 5.89 km. [Case-level frequency, rival and geographic scores](scores.json)

Across development and holdout, all 11 containing queries forced the correct region and 9/11 forced coordinates were within 5 km. Their 3.37 km forced median compares with 3.05 km for the earlier full-offer archived receiver. The prior all-capture archived grid also made zero publications. The earlier worldwide offset-only receiver issued one publication 9,471 km from GNSS across the same four held sites. The anonymous simultaneous-only approach also withheld its 33 matched decisions. These endpoints show coarse region evidence with suitable offers and repeated failure to validate an unassisted coordinate on this measured panel. [Earlier full-offer receiver](../../../2026_11_18_blind_regional_receiver/README.md) · [Earlier worldwide receiver](../../../2026_11_19_short_receiver/physical-transfer/README.md) · [Earlier simultaneous pair method](../../next/anonymous-transfer/README.md) · [All-capture figure](charts/c0/field_anonymous_doppler_all.png)

The sealed worker batch took 115.4 s on CPU 2 at nice 10, including process isolation and decoding but excluding preliminary MAT staging and any prior acquisition. The source lock records Python 3.12.14, Clang 22.1.3, NumPy, SciPy, and the SHA-256 of the accelerated SGP4 extension. There is no custom numerical extension to build for this variant. [Position archive](positions.jsonl.gz) · [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [Figure manifest](figures.json)

## Reproduce

Copy the protocol into an unused output directory and supply the existing StarLoc MAT root. The figure command can also render from these sealed results directly.

The replay's source lock records the original Python bytes. The two measured files reflowed during formatting are preserved under their repository-relative paths in the source archive. Extract it into a separate repository copy to reproduce the original source hashes. The format receipt verifies that the parsed Python syntax trees are unchanged. [As-measured source archive](as-measured-source.tar.gz) · [Format receipt](source-format-receipt.json)

```sh
cp reports/2026_11_19_receiver_screening/acquisition-support/field-anonymous/PROTOCOL.md "$OUTPUT/"
nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  TMPDIR="$BULK_SCRATCH" taskset -c 2 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.field_anonymous_trial predict \
  --raw "$STARLOC_MAT_ROOT" --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.field_anonymous_trial score --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.field_anonymous_figures \
  --evidence "$OUTPUT" --render "$OUTPUT/charts"
```
