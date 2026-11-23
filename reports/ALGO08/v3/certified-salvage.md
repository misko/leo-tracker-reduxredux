# Exact support pruning in saved ALGO08v3 solves

Certified salvage cut the dense saved solve from **27.667 to 25.661 CPU seconds**, saving **2.006 CPU seconds** against a fresh matched control and **2.791 seconds** against the archived 28.452-second run. The experiment missed both the five-second saving and the 24-second solve target. All three saved decisions, both RF fits and positions, the returned owners and roles, the recovery alternatives, and the complete numerical path and grid matched the prior solver. The dense control already returned its ordinary fit after signed qualification failed. The prototype preserves that decision, including its existing loss relative to the full-catalogue signed fit. [Frozen protocol](certified-salvage-protocol.md) · [Scored timings](measurements/certified-salvage-summary.json) · [Full receipts](measurements/certified-salvage.json.gz)

## Feasibility and ranking checks

At each original phase, let `rᵢ` be the original rounded `observed − RF × Doppler` at observation `i`. To pass the stock six-sigma pointwise residual gate and the 3 kHz fitted-bias gate, every point must admit the same `bias − alias_shift` inside the interval `[rᵢ − Lᵢ, rᵢ + Lᵢ]`. The existing binary64 bound `Lᵢ` accounts for division and residual arithmetic, and both interval endpoints round outwards again. This condition allows any common shift, so failure rules out even a more permissive fit. A phase can survive only while the running maximum of the lower bounds is at most the running minimum of the upper bounds and all points remain visible. Prefix and suffix passes cover every original candidate window because salvage offers only whole, prefix and suffix supports. A support can be removed when every original phase fails one of these necessary conditions. Unresolved supports run the original profile across all 121 phases and apply the unchanged gates to its original minimizing phase. This preserves cases where the minimizing phase fails a gate and another phase could have passed.

The original salvage returns five alternatives ordered first by descending support size. Once a longer size has yielded five valid alternatives, every strictly shorter support is dominated. The code examines all ties at the cutoff size and preserves the original stable order by satellite and support indexes. The original inside/outside candidate widening rule still sees the same ranked results. The separate coarse change groups adjacent rejected tracks under a 96 MiB estimated projection workspace, evaluates the same nominal full-catalogue projection on deduplicated timestamps at the exact original receiver coordinate, and gathers each track's columns in its original order. The matched baseline records the original full shortlist for every salvage track. [Implementation](certified_salvage.py) · [Tests](../../../tests/pipeline_eval/test_certified_salvage.py)

## Measured scope

| Saved offer | Solve CPU s, fresh → certified | Complete salvage CPU s, fresh → certified | Publication |
|---|---:|---:|---|
| DS30-0008 | 27.667 → 25.661 | 5.224 → 2.540 | Ordinary fit, 4,244 owners per arm, 179 grid points |
| Southern containing | 3.101 → 3.090 | Stage unused | Signed fit, 266 owners per arm, 137 grid points |
| Southern displaced | 6.034 → 5.959 | 0.446 → 0.254 | Withheld by both receivers' exterior evidence |

The dense proof rejected 42,700 of 47,403 support trials. Strict length dominance removed another 1,773. The remaining 2,930 used the exact phase profile, and 383 reached the original polynomial noise screen. Paid fine salvage fell from **3.863 to 1.302 CPU seconds**. The candidate spent 1.075 CPU seconds preparing exact fine geometry and feasibility certificates and 0.198 seconds profiling and gating unresolved supports. The three coarse groups reused 73 timestamp columns and reduced measured coarse geometry and projection from 0.887 to 0.784 CPU seconds. All 49 dense shortlists and all 10 displaced-south shortlists matched. The containing south never entered salvage. Each case exercised the original paired qualification, and the full route fallback count was zero. The dense clock includes the failed warm signed attempt and the original signed refit. Numerical publication evidence remained charged at 6.120 CPU seconds on dense. PNG rendering and acquisition were outside both matched clocks. [Stage and fallback clocks](measurements/certified-salvage-summary.json)

| Saved offer | RF RMS in Hz, `c = 0` / fitted | Horizontal error in km, `c = 0` / fitted | Error change vs installed in km | Error change vs full-catalogue signed in km |
|---|---:|---:|---:|---:|
| DS30-0008 | 129.457 / 129.444 | 1.464 / 1.506 | −0.175 / −0.006 | +0.377 / +0.426 |
| Southern containing | 6.499 / 6.391 | 0.791 / 1.086 | −0.026 / −0.016 | −0.026 / −0.016 |
| Southern displaced | Withheld | Withheld | — | — |

Against the lighter-estimator controls, both arms changed by exactly zero in RF RMS, horizontal error, conditional and predictive ownership, and numerical grid and path. Dense ownership still differs from full-catalogue signed because these routes use the earlier representative-family solver. Relative to that signed control each arm changes NORAD on 197 shared observations, loses 291 and gains 95. Both southern outcomes use the same simulated saved detections and different offered regions. The false-region control preserved its terminal withholding and both arms' attempted fit. Its original exterior comparison cost 2.900 CPU seconds in the fresh control. [Paired errors and owner differences](measurements/certified-salvage-summary.json)

## Remaining budget

The fresh baseline's entire salvage stage costs 5.224 CPU seconds. Removing the candidate's remaining **2.540 CPU seconds** of salvage for free would put its complete solve at **23.121 seconds**. A five-second saving against the matched fresh control would require **22.667 seconds**. The remaining dense closure and standard publication stages charge **7.098** and **6.120 CPU seconds** respectively. The actual grid already passes 356 native posterior factors to its prediction stage. That leaves 3.387 CPU seconds for the curved calls and 1.709 for prediction, with the existing exact objective and grid intact. Earlier cross-arm projection and native handoff trials cover related boundaries. No grid acceleration is counted here. [Final-estimator control](lighter-joint-estimator.md) · [Existing posterior handoff](../single-core-2x/solver-posterior-handoff.md) · [Full receipts](measurements/certified-salvage.json.gz)

## Reproduce on Gauss

Use two new empty writable output directories for the matched controls and certified runs. For each of `DS30-0008`, `south-containing` and `south-far`, set `mode` to `control` then `certified` and set `output` to that mode's new case path. The runner opens existing sealed observations and causal catalogues, and verifies unchanged provenance. The `score` subcommand takes the certified directory, a new summary path, a new compressed-receipt path and `--salvage-control` with the matched control directory. It compares scientific fields and all coarse shortlists before reading the scoring reference.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 125s \
  sudo -n -u leo env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/representative_family_pool_trial.py \
  run "$case" "$output" --salvage-audit "$mode"
```

Thirty-four focused tests passed under that same CPU and thread allocation. They cover an interior-only residual contradiction, visibility and rounding boundaries, tied alternatives, strict length dominance, numeric fallback and equal gathered projection columns. This is a saved research route. [Focused tests](../../../tests/pipeline_eval/test_certified_salvage.py)
