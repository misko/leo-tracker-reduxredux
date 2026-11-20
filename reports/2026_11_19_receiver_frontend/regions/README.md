# Longitude controls for missing receiver regions

On the frozen synthetic panel, the longitude check reduced missing-offer false
fixes from 6 to 2 of 40. It retained every published true fix on the frozen and
fresh panels. The fresh panel had no false fixes under either method. On
StarLoc and DS29 the gate left both region and publication decisions unchanged.

The arc endpoint receiver can find a good Doppler fit among four wrong offers.
This experiment challenges an accepted regional nomination with the same search
over 19 rigid longitude rotations of the offers. Each control preserves the
offer latitudes and spacing and uses the same anonymous CFO tracks, causal
catalogue, candidate cap and 25 km fit. A control that equals or exceeds the
offered winner's held endpoint score vetoes region acceptance. The gate keeps
the original forced position as a diagnostic and publishes only original arc
fixes that pass all controls. [Frozen protocol](PROTOCOL.md)

The 20 group phases give a nominal 1-in-20 rank tail if the absent-offer
longitude phase is exchangeable. The measured and simulated offer construction
does not ensure that condition. A false offer near the actual receiver can
carry real Doppler evidence, and a rotated control can support an unrelated
pass by chance. The missing-offer counts measure the resulting decision rule
on these panels.

## Position and region decisions

Each row gives paired present and missing attempts. The region column counts
false region decisions before the position boundary check. The error columns
give median, P95 and maximum geodesic error in kilometers. Published and
forced error distributions on present offers are identical for the two
methods. [Per-query and group scores](scores.json)

| Corpus | Attempts per condition | Present fixes, both | Present within 5 km, both | Present published error, both | Present forced error, both | Missing false region, arc → rotation | Missing false publication, arc → rotation |
|---|---:|---:|---:|---:|---:|---:|---:|
| StarLoc | 11 | 8 | 8 | 2.593 / 3.874 / 4.010 | 2.853 / 7.146 / 8.386 | 5 → 5 | 0 → 0 |
| DS29 | 8 | 7 | 3 | 5.343 / 5.983 / 6.055 | 5.440 / 6.814 / 7.222 | 4 → 4 | 0 → 0 |
| Historical synthetic | 40 | 36 | 26 | 3.600 / 10.012 / 12.155 | 3.528 / 9.851 / 12.155 | 11 → 4 | 6 → 2 |
| Altrincham empty recordings | 3 | 0 | 0 | — | — | 0 → 0 | 0 → 0 |
| Fresh synthetic | 40 | 32 | 21 | 3.957 / 11.747 / 13.456 | 4.183 / 12.313 / 13.456 | 3 → 1 | 0 → 0 |

Both methods nominated and accepted the correct region for every present
offer with usable tracks. The publication boundary then withheld some
positions. The two surviving historical synthetic false fixes were 112.5 km
away for a neighboring masked scene and 7,326.0 km away for a dispersed open
scene. On the fresh panel, both vetoes removed already-withheld false regions.
The original arc receiver had two false fixes on an earlier fresh seed, while
it produced zero here. This run independently demonstrates retention of fresh
true fixes and fewer fresh false region accepts. Its publication improvement
is established only on the historical synthetic panel. [Earlier confirmation](../../2026_11_19_receiver_streaming/field/confirmation/README.md)

## Held frequency evidence and compute cost

The check reuses the original orbit, time-shift and frequency-offset fit for
every emitted position. Median held RMS on the published present fixes was
159 Hz on StarLoc, 216 Hz on DS29, 229 Hz on historical simulations and 227 Hz
on fresh simulations. These RMS values describe only supported endpoint
samples. The selected StarLoc missing offers had a 315 Hz median RMS across
the 10 cases with available held residuals. The two calibration arms were
identical on every result. Each track uses a fixed RF, so its fitted frequency
offset absorbs a constant RF-dependent calibration in both offered and
rotated tiles. A unit test injects independent per-track offsets through the
full decision. [Sealed predictions](predictions.jsonl.gz)

Median present-query localization time rose from 1.05 s to 14.75 s on the
transfer panel and from 0.92 s to 13.87 s on the fresh panel. The combined
qualification took 733 s wall-clock on three CPU cores. The 122 eligible
queries consumed 8,725 control tile nominations. The additional search cuts
chance regional matches in some simulated cases while retaining measurable
false accepts and adding an order of magnitude to receiver runtime on present
offers. The evaluation starts at prepared anonymous tracks. [Prediction lock and timing](prediction-lock.json)

## Reproduction

The predictor uses portable tracks and causal TLEs. The original 124 frozen
inputs and the new 80 synthetic queries are passed to the same implementation.
The synthetic panel uses the unchanged generator with its own seed and 40
sites over 12 capture days. The source lock precedes generation. The scorer
requires an intact prediction seal before opening answers. The run used one
numerical thread on each of CPU cores 17–19.

Every portable observation and catalogue on the frozen panel matched its
registered hash. All rerun baseline results matched the previous arc output
after excluding timing. The new generator's seed commitment differs from
both previous seeds. [Source lock](algorithm-lock.json) · [Generator receipt](holdout-receipt.json) · [Released seed](fresh-seed.hex)

```sh
region_trial_base=$(mktemp -d /tmp/leo-longitude-qualification.XXXXXX)
region_trial_root=$region_trial_base/panel
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m tools.pipeline_eval.qualification.off_region_eval prepare "$region_trial_root"
taskset -c 17-19 .venv/bin/python "$region_trial_root/holdout_private/publish.py"
taskset -c 17-19 .venv/bin/python -m tools.pipeline_eval.qualification.off_region_eval predict "$region_trial_root"
.venv/bin/python -m tools.pipeline_eval.qualification.off_region_eval score "$region_trial_root" "$region_trial_base/scored"
```
