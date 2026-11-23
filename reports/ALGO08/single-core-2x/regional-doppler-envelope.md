# Regional Doppler exclusions in ALGO08v3

The bounded Doppler and visibility envelope rules out **84.7–92.3%** of whole-track edges in the saved preparations when orbital phase is confined to ±15 seconds and the orbit error lies within the specified position and velocity balls. Northern containing and far-omitted offers exclude nearly the same number of edges on identical detections. The envelope provides no position decision on those offers. Frozen v3’s broad discovery and cavity stages use finite scores to nominate alternatives, so the envelope establishes **zero exact whole-pipeline RF edge deletions** at those stages. Fine salvage has a narrower hard gate where a complete support can be removed. [Saved trial and reproduction](regional_envelope_trial.py)

## Whole-square audit

Use the frozen graph tracks, observation epochs, region, causal catalogue, and frequency scale. From the offered center, enclose the entire WGS84 zero-height rectangle by integrating the geodetic metric with a 6,450 km curvature-radius ceiling. This gives an observer ECEF radius and an angle bound on the local up vector. At an epoch and nominal phase, if the combined observer and satellite position error is `δ` and the nominal slant range is `r`, the line-of-sight direction changes by at most `δ/(r−δ)` radians. The Doppler margin follows by multiplying by the nominal speed, adding the satellite velocity error, and multiplying by the RF-to-light-speed ratio. The elevation margin adds the local up-angle change. Valid range checks and outward padding keep unresolved comparisons. [Bound implementation](../../../tools/pipeline_eval/variants/experimental/regional_envelope.py)

For continuous phase, divide ±15 s and ±30 s into 5-second tiles. Each tile bounds motion away from its midpoint using the largest causal interpolation-knot slope and the Earth rotation rate. The uncertainty arm adds a 10 km satellite position ball and a 0.02 km/s velocity ball independently at every endpoint. These are sensitivity inputs, with no calibrated confidence or universal authority for TLE errors. Tiles that would need extrapolation retain the corresponding hypotheses. All hypotheses in every tile must fail for the complete edge to count. The audit considers two actual observation endpoints per track, and a necessary condition failing at either endpoint or on the endpoint contrast suffices. The remaining observations can only add requirements for full-track eligibility.

Within each whole track, differencing cancels the constant receiver offset, Gaussian bias, fitted `c` at that RF and every integer native alias. The contrast allows 31.5 Hz/s of drift and all receiver basis coefficients in ±2,000 Hz. The necessary condition for a 450 Hz RMS gate is that the error contrast be at most `450 sqrt(2n)` for `n` observations, before adding those receiver and geometry margins. The same census applies to fixed-zero and fitted `c` because their constant contributions cancel.

| Saved input and offer | Graph tracks | Conditional whole-track edges excluded, ±15 s with orbit balls | Horizon alone | Curved edges excluded | Satellites excluded against every whole track | Census CPU s |
|---|---:|---:|---:|---:|---:|---:|
| Dense physical DS30-0008 | 236 | 309,228 / 348,336 | 225,391 | 157,122 / 163,836 | 702 / 1,476 | 1.081 |
| Lower-density physical DS30-0374 | 125 | 162,401 / 175,875 | 113,967 | 89,380 / 92,862 | 785 / 1,407 | 0.591 |
| Northern simulation, containing | 31 | 42,782 / 48,639 | 31,696 | 21,828 / 23,535 | 1,175 / 1,569 | 0.195 |
| Southern simulation, containing | 30 | 41,137 / 48,540 | 30,794 | 20,434 / 22,652 | 935 / 1,618 | 0.183 |
| Northern simulation, far omitted | 31 | 42,767 / 48,639 | 31,644 | 21,820 / 23,535 | 1,173 / 1,569 | 0.178 |

At ±30 s with the same orbit balls, the corresponding whole-track edge exclusions fall to 248,402, 129,875, 30,456, 29,966 and 30,462. Each case has at least one track with uncovered phase, leaving **zero** satellite-wide removals in every case. The counts use the already screened causal bank. A satellite excluded from every complete graph track can still appear in a cropped salvage support or an exterior probe. The original catalogue and graph stay available to those stages.

## Frozen scoring and the exact boundary

The discovery association returns the lowest visible-cost nominee even when it fails every hard compatibility gate. Continuation takes this nomination and its diagnostics. Fresh phase proposals also use top-k scores and explicit preferences, while the late cavity keeps up to seven finite broad alternatives in addition to the current owner. A Gaussian or robust finite residual contributes to these comparisons even far beyond the curve’s compatibility threshold. Later orbit modes and receiver coefficients also enter Gaussian factors with unbounded support. A safe finite-score deletion needs bounds on each relevant ranking or objective against an incumbent, with the original ties, alias layout, normalization, observations and alternatives preserved. [Discovery](../../../src/leo/analysis/localization_v3/scan.py) · [Continuation](../../../src/leo/analysis/localization_v3/families.py) · [Cavity alternatives](../../../src/leo/analysis/localization_v3/family_cavity.py)

Fine salvage uses the existing fixed-zero fit to set receiver terms, then searches the original 121 discrete phases over each shortlisted track support. It keeps only the best penalized visible phase and separately requires the maximum standardized residual to be at most six. For each support endpoint pair, subtract the measured and nominal Doppler contrast after that same fixed receiver correction. A passing phase requires the absolute contrast to fit within the two outward-rounded residual limits plus both regional Doppler margins. A below-horizon endpoint over the entire square is independently sufficient. The scoped patch skips an entire shortlist support only if every original phase fails at least one of those necessary conditions. Every surviving support keeps the stock minimum-cost phase search, where the winning phase can fail a later gate even when the second phase might pass. The guard retains the original coarse shortlist, diagnostics counts and support order. An unsupported bank, numerical input or projection binding uses the original phase loop. The receiver geometry uses the supplied square and the current solver's trial point. [Fine-salvage policy](../../../tools/pipeline_eval/variants/v5_tiled_salvage.py) · [Earlier exact fixed-site endpoint test](solver-salvage-bound.md)

The earlier dense profile attributed 8.130 CPU seconds to all initial ranking and 5.028 seconds to all fine salvage on DS30-0008. Removing the entire latter boundary would be a ceiling of 1.080× on the 67.759-second profiled saved solve and 1.047× on the 111.082-second installed-v3 raw CPU clock. The earlier 2.492-second fine-salvage profile on DS30-0374 implies 1.040× on the installed-v3 raw CPU clock of 64.395 seconds. These are optimistic cross-profile ceilings, including work the guard cannot remove. [Dense stage accounting](restored-scout-0008-solver-profile.md) · [Earlier salvage profile](solver-salvage-bound.md)

## Whole saved solves

The comparison checks the decisions, both calibration positions and RF RMS, per-arm owners and associated counts, the original ordered salvage nominations, the sampled position grid, optimizer path, endpoint score replay and exterior-guard evidence. The grid digest excludes its measured `elapsed_seconds` field. All grid points and their numerical values remain in the digest. An equivalent measured guard on an omitted offer leaves both coordinates null through the existing exterior rule.

| Saved input and offer | Fine supports skipped | Shortlisted trajectories skipped | Guard CPU s | Saved solver CPU, stock → guard (s) | Saved solver wall, stock → guard (s) | Exact decision and numerical evidence |
|---|---:|---:|---:|---:|---:|---|
| Dense physical DS30-0008 | 8,699 / 40,189 | 11 / 1,047 | 0.851 | 54.887 → 54.485 | 55.352 → 54.519 | Both fixes, 4,472 owners per arm |
| Lower-density physical DS30-0374 | 3,510 / 11,911 | 23 / 365 | 0.274 | 22.683 → 21.702 | 23.135 → 21.704 | Both fixes, 2,905 owners per arm |
| Northern simulation, containing | 0 / 0 | 0 / 0 | 0 | 5.940 → 5.635 | 5.941 → 5.636 | Both fixes, 302 owners per arm |
| Southern simulation, containing | 0 / 0 | 0 / 0 | 0 | 4.647 → 4.679 | 4.648 → 4.679 | Both fixes |
| Northern simulation, far omitted | 146 / 945 | 4 / 91 | 0.032 | 9.470 → 10.247 | 9.470 → 10.253 | Both arms withheld by the frozen exterior rule |

All exclusions in these fine loops required the RF contrast. The conservative-recovery wall time shifted from 12.887 to 12.769 s on the dense case and 4.193 to 3.925 s on the lower-density case. Untouched initial ranking shifted by 0.281 and 0.808 s respectively, and the northern containing trial shifted by 0.306 CPU s with zero guard work. The omitted offer's audit computed all 945 original profiles with the bound active as an observer and retained the same decisions and trims. Fine-loop CPU shifted from 0.120 s in that audit to 0.108 s when the 146 certified skips activated. The complete omitted solve cost more with the guard. The measured recovery differences stay below one third of a second. [Matched saved receipts](measurements/regional-doppler-envelope.json)

## Reproduction

The installed ALGO08v3 runner binds the frozen specification, stored detector document, original terminal, supplied offer and complete causal snapshot digest. The omitted control reuses the exact northern detections and causal archive with the separately published far offer. All solver clocks cover saved detections through the numerical result. Each count or solve uses the shared Gauss lock, CPU 2, low CPU and I/O priority and one numerical thread. [Independent public-region development evidence](../regional-release/README.md) · [Component tests](../../../tests/pipeline_eval/test_regional_envelope.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
frozen=/opt/leo-algo08/algo08v3/payload
bench=/tmp/leo-algo08v2-2x-bench
pair=/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications/DS30-0008/pair.json
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$frozen:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 \
  timeout 135 "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/regional_envelope_trial.py \
  "$pair" /var/tmp/regional-envelope-dense-census.json --mode census
```

`--mode stock` runs the frozen solver, `--mode audit` runs the guard and checks every admitted alternative, and `--mode prune` skips certified fine supports. Supply a different published region with `--alternate-offer`. The optional paired-publication adapter loads and verifies the source after the frozen lazy-startup hook and exposes per-solve counters. [Adapter](../../../tools/pipeline_eval/variants/experimental/regional_envelope_install.py)
