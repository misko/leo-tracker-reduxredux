# Lighter fixed-owner estimation and family confidence

The combined candidate reduced dense saved-solver CPU from **30.223 s to 28.452 s**, with identical returned positions, RF residuals, owner rows, numerical grid and optimizer path. It missed the 24 s timing target and the full-signed position tolerance. The dense warm signed attempt reached neither arm's stationary stop within its two-refresh limit and added 0.611 CPU s before the original signed refit. The measurable dense saving came earlier, where exact family-weight selection reduced the combined initial and predictive stages from **4.546 s to 2.205 s**. [Frozen protocol](lighter-joint-estimator-protocol.md) · [Numeric summary](measurements/lighter-joint-estimator-summary.json) · [Sealed receipts and owner rows](measurements/lighter-joint-estimator.json.gz)

## Saved outcomes

| Offer | Installed CPU (s) | Full signed CPU (s) | Iterative control CPU (s) | Candidate CPU / elapsed (s) | Terminal result | Grid points |
|---|---:|---:|---:|---:|---|---:|
| DS30-0008 | 60.966 | 39.045 | 30.223 | 28.452 / 28.463 | Ordinary paired fix | 179 |
| South containing | 4.620 | 3.878 | 3.817 | 3.102 / 3.102 | Warm signed pair | 137 |
| South displaced | 6.400 | 6.794 | 6.931 | 6.473 / 6.481 | Exterior withholding | — |

The dense cold component retry took 2.252 CPU s and reached the same signed paired RF rejection as the iterative control. The ordinary pair returned with all 4,244 exact owners and roles in both arms. Both southern warm pairs finished in two refreshes. Their signed fit times were 0.032 s on the containing offer and 0.025 s on the displaced offer, against 0.082 and 0.098 s for the iterative control's original cold signed fits. The containing result retained all 266 owners and roles. Its two endpoints and scientific path and grid values changed with the warm start. Both returned grids met the original objective replay check exactly. The distant offer withheld for the original two-receiver exterior condition. No run needed a full-route fallback.

| Offer and mode | \(c=0\) error (km) | Fitted \(c\) error (km) | \(c=0\) RF RMS (Hz) | Fitted \(c\) RF RMS (Hz) |
|---|---:|---:|---:|---:|
| Dense installed v3 | 1.638978 | 1.511956 | 129.703040 | 129.662931 |
| Dense full signed | 1.086273 | 1.079543 | 128.821374 | 128.753307 |
| Dense iterative and candidate, ordinary | 1.463735 | 1.505753 | 129.457118 | 129.443925 |
| South containing, full controls and iterative | 0.816789 | 1.101409 | 6.502299 | 6.391940 |
| South containing, warm signed | 0.791086 | 1.085591 | 6.499045 | 6.390572 |

Dense remained 0.377462 and 0.426210 km worse than full signed. It kept the iterative route's 4,149 shared observations with full signed, including 197 NORAD changes and no role changes. The slightly lower southern errors are a result on one containing offer with unchanged owner assignments. The displaced control verifies withholding and has no returned error or RF RMS.

## What the faster path removes

The released fixed-owner likelihood already integrates the linear nuisance design inside the posterior solve. Its bounded Gauss–Newton and secant path checks trial steps against that full residual objective. The warm version reuses each arm's own ordinary endpoint and posterior phase as a starting state for the changed signed means, with up to two original exact fits. It requires small-step, displacement, phase and original paired RF checks before the two arms can replace the normal signed fit. The robust terms, nuisance elimination, exact orbit calculation and final evidence remain active. The older profiled-Gamma work instead changes how the inner Gamma rates converge. Schur and affine experiments change factorization or trial matrix construction. The prior cross-arm geometry study measured 0.137 s of sharing opportunity on DS30-0374. [Profiled Gamma](profiled-gamma.md) · [Schur](../single-core-2x/solver-schur.md) · [Affine proposal](../single-core-2x/solver-affine.md) · [Cross-arm geometry](../single-core-2x/solver-grid-cross-arm.md)

The exact confidence change uses the released `cross_rx_support` rule. Two-receiver families always get weight 1, and single-lane families always get 0.2. Only active tracks in replicated single-receiver families can flip between 0.2 and 0.6 based on the confidence threshold. The candidate uses the original nuisance state and full causal catalogue to score those rows at the same five anchors. It projects only the exact active timestamps read by those rows. A component test compares the actual consumed family weights exactly, including partial masks. On dense, four confidence calls needed 27, 18, 20 and 20 active tracks out of 111, 62, 104 and 84. The corresponding time grids used 1,034, 717, 734 and 742 out of 4,079 original timestamps. Those calls took 2.028 CPU s together. Both southern cases had zero confidence-sensitive rows and skipped all catalogue projections in this stage.

| Dense stage | Iterative control CPU (s) | Combined candidate CPU (s) |
|---|---:|---:|
| Cold catalogue closure | 7.194 | 7.561 |
| Initial gate | 2.289 | 1.596 |
| Salvage, with initial weighting for the post-gate state | 5.873 | 5.373 |
| Predictive nomination and its preceding weight checks | 2.257 | 0.608 |
| Ordinary exact paired fit | 0.901 | 0.902 |
| Signed qualification and evaluation, including warm and cold work | 2.310 | 2.948 |
| Standard numerical evidence | 5.926 | 5.857 |

The control clocks came from the earlier separately sealed matched solves. With the same inputs and unchanged dense scientific outputs, the combined gate and predictive timing reduction is attributable to the weighting boundary, with normal inter-run timing variation. Erasing both remaining dense ordinary and signed fit clocks would still leave about **24.602 CPU s** at the measured other-stage rates. Cold closure, salvage and numerical evidence alone consumed 18.790 CPU s. This identifies the scale of work outside the final estimator for a 10-second target.

## Reproduce

Use the original saved detections, causal archive and offered regions on the shared Gauss CPU. The score step opens the position references after the three runs seal. The clock starts at saved detections and ends at the numerical evidence or withholding decision. Waveform acquisition and PNG rendering are outside that boundary.

```bash
runner=reports/ALGO08/v3/representative_family_pool_trial.py
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/lighter-joint-estimator.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 125s \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for case in DS30-0008 south-containing south-far; do
  gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
    "$release/venv/bin/python" -BPs "$runner" run "$case" "$out/$case.json" --lighter-estimator || exit
done
gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" \
  "$release/venv/bin/python" -BPs "$runner" score "$out" "$out/summary.json" "$out/full.json.gz"
```
