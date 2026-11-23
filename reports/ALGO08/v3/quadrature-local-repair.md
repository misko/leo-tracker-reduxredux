# Can local reassociation recover the failed quadrature tracks?

The local RF screen found **zero eligible assignments among 450 full-observation hypotheses** on the sealed dense quadrature failure. It took **0.067 CPU s** to rebuild the two calibrations and test all 25 surviving causal families on all nine failed tracks in both calibration arms. The results left every rejection count above the unchanged 5% cap. The frozen feasibility rule stopped before a new paired position fit and the southern panel. [Protocol](quadrature-local-repair-protocol.md) · [RF and timing receipt](measurements/quadrature-local-repair-rf.json) · [Sealed stock overlap audit](measurements/quadrature-local-repair-audit.json)

| Repair support | Original proposed support | Would be discarded after local screen | Maximum allowed discard | Minimum restoration required |
|---|---:|---:|---:|---:|
| Tracks | 153 | 10 | 7 | 3 |
| Curved observations | 3,667 | 252 | 183 | 69 |
| Predictive observations | 960 | 78 | 48 | 30 |

The exact quadrature replay matched the sealed input, support, failed two-arm fit and rejection counts. The local screen used the original measured points and signed alias calculation. Each arm recalculated its own receiver and phase posterior from only the surviving curved observations at its frozen endpoint and phase reference. It screened each candidate with the inherited conditional geometry, profile, noise and visibility tests. The allowed labels already had compatible curved support. A nomination required the same owner and alias in both arms. No candidate passed even one arm. Three failed curved tracks had no surviving incumbent family, and their best remaining full-interval RF RMS exceeded 937 Hz in both arms. For the other six targets, the original owner had the lowest RF RMS, each below 450 Hz in both arms. Those incumbent fits still failed the full RF screen. The experiment bounds reassignment among surviving families at these frozen calibration states. New-family discovery, additional phase searches, changed trim intervals and joint moves of the calibration were outside the local screen.

The separate audit opened the archived stock owner map after the RF result was sealed. Stock used 77 of 79 and 41 of 45 observations on two failed curved tracks, assigned to the same original satellite on each in both arms. It used zero observations on the other seven screened targets, including all three failed predictive tracks. Thus simply substituting stock's observed assignments on the failed support shows no alternate owner and no evidence toward the 30 predictive observations needed to meet the cap. Dropping the failed curved support would additionally orphan 20 predictive observations, bringing the total predictive loss from 58 to 78. The overlap identifies where stock found usable evidence under its own fit and trim. It supplies no new input to the diagnostic.

| Dense cost | CPU (s) |
|---|---:|
| Replayed quadrature and local RF diagnostic, charged | 17.635 |
| Healthy-calibration reconstruction, within diagnostic | 0.035 |
| Nine-track RF screen and cap arithmetic, within diagnostic | 0.032 |
| Full signed control cold discovery and salvage, sealed | 19.015 |
| Installed fallback after original quadrature, sealed | 51.330 |
| Fresh installed control, sealed | 60.966 |
| Full signed control, sealed | 39.045 |
| Projected local direct path with matched signed and grid charges | 26.491 |

The diagnostic left 6.365 s under the 24 s dense timing screen. The full signed control's original grid and numerical evidence alone took 6.511 s. Charging the sealed signed-refit, exterior and grid stages gives 26.491 s even before any new exact paired refit. Adding the prior measured incremental installed fallback to the diagnostic would cost approximately 68.965 CPU s. Both are projections on matched prior stage clocks. The runner records `sealed_local_reassociation_diagnostic` as its completion status. It produces no localization publication or grid. The established fallback, signed refit, exterior veto and real-grid requirements remain in force for any publishable route.

## Reproduce

Run from this checkout with read access to the archived detector and current pinned installed release. The two commands keep the sealed diagnostic before the audit reads the earlier stock labels.

```bash
runner=reports/ALGO08/v3/quadrature_local_repair_trial.py
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/quadrature-local.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 75s \
    env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$release/venv/bin/python" -BPs "$runner" "$@"
}
gauss run "$out/rf.json"
gauss audit "$out/rf.json" "$out/stock-audit.json"
```
