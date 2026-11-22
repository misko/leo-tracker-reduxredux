# Shared orbit-frame rotation at the mirrored boundaries

The later generator catalogue differs from the capture-causal catalogue by a median shared yaw of **0 arcsec** over 10,935 matched satellites. Restricting the comparison to 5,557 genuinely newer element epochs gives **+2.574 arcsec**, equivalent to 54 m east–west in the north and 67 m in the south. A 200 m translation requires **9.606 arcsec** and **7.700 arcsec**, respectively. The fitted yaw from the newer elements leaves both wrong face classifications in place. The pre-capture forecast also failed its held test, so it supplied no correction. [State fits and complete face scores](measurements/mirrored-yaw.json) · [Prespecified procedure](mirrored-yaw-protocol.md)

## What the orbit states identify

Rotating satellite positions, velocities and the receiver together around the spin axis preserves retarded range, Doppler and elevation in the symmetric geometry. The existing projection regression covers this symmetry. A shared orbit rotation could therefore appear as a receiver longitude offset if the orbit frame itself were unconstrained. This experiment measures differences between the independently published element sets. It cannot measure a rotation common to every observed revision. [Existing joint-rotation regression](../../../tests/pipeline_eval/test_algo08_cavity_projection.py#L62)

The fit compares position and velocity at identical TEME epochs, each normalized by its nominal magnitude. It removes each satellite's own time-shift tangent before estimating the spin-axis angle. This separates a fixed common rotation from the leading along-orbit phase mode. The retained yaw-tangent norm was 55.1% at the fifth percentile and 68.7% at the median. An independent check using propagated orbital-plane normals gave +2.674 arcsec on the newer elements. This state geometry makes the revision angle estimable in the evaluated frame. It leaves any absolute frame gauge intact.

| Later versus causal population | Matched orbits | Median yaw, arcsec | Per-orbit fifth to 95th percentile, arcsec |
|---|---:|---:|---:|
| All identifiable | 10,935 | 0.000 | −8.187 to +16.233 |
| Genuinely newer element epochs | 5,557 | +2.574 | −14.715 to +24.143 |
| Northern selected owners | 12 | 0.000 | −6.910 to +2.822 |
| Southern selected owners | 13 | 0.000 | −2.433 to +16.676 |

Among newer elements, median yaw by inclination group ranged from −1.745 to +5.455 arcsec. Applying the fleet median removed 0.31% of the state residual energy after along-track projection. The dispersion and changes of sign across groups are compatible with diverse individual orbit updates. The subsets and time sequence share catalogue production and dynamics, so these spreads describe the observed revisions and do not give a confidence bound on a correlated fleet rotation.

## Past-only forecast and face scores

The two causal training transitions yielded +0.654 and +0.768 arcsec. Their collection intervals were two hours each, giving the frozen rate +0.356 arcsec per hour. Both held predictions were +0.711 arcsec. The held measurements were effectively zero across 5,086 updated orbits and +12.669 arcsec across two updated orbits. The first forecast lost to zero. The second held snapshot's two newer epochs also provide little evidence about a fleet rotation. The prespecified gate left both capture predictions at nominal yaw. [Sealed past-only fit](measurements/mirrored-yaw-lock.json)

A and B are the two synthetic positions across the midpoint face. A is outside in the north and inside in the south. The evaluator scores each noiseless later-orbit position against both causal templates using the original clock, track and orbital-phase nuisance projection. The track offsets absorb the constant fitted RF calibration term. Both gauges therefore share these contrast outcomes. The fleet-wide oracle median of zero and the gated causal predictor reproduce the nominal rows.

| Public site and causal-bank rotation | True A scores against A / B, Hz RMS | True B scores against A / B, Hz RMS | Chosen for true A / B |
|---|---:|---:|---|
| North, nominal | 6.696 / 7.281 | 6.251 / 6.785 | A / A |
| North, newer-element oracle median | 6.548 / 7.120 | 6.120 / 6.636 | A / A |
| North, +200 m yaw | 6.165 / 6.697 | 5.787 / 6.252 | A / A |
| North, −200 m yaw | 7.280 / 7.907 | 6.783 / 7.370 | A / A |
| South, nominal | 1.727 / 2.739 | 1.223 / 1.736 | A / A |
| South, newer-element oracle median | 1.464 / 2.379 | 1.288 / 1.474 | A / A |
| South, +200 m yaw | 1.214 / 1.728 | 1.728 / 1.223 | A / B |
| South, −200 m yaw | 2.738 / 3.875 | 1.735 / 2.744 | A / A |

The positive artificial rotation is large enough to change the southern face score, which demonstrates the possible effect of a real longitude-frame error. Its magnitude has no support from the fitted common update. The northern contrast still chooses A at the same geographic rotation scale. These are fixed-owner conditional tests on one later generator revision and two public waveforms. A different orbit model or an independent frame reference could change what is identifiable. [Prior causal forecasts](mirrored-causal-forecast.md) · [Conditional orbit and radio noise](mirrored-noise.md)

## Reproduce

The first process fits and seals the causal history. The second verifies the lock and the nominal bank before opening the after-capture generator orbit. Both stages used one low-priority core on Gauss. Sixteen targeted tests passed, including a circular inclined-orbit control, an equatorial phase/yaw degeneracy and the existing joint-rotation regression.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
archive=/tmp/leo-regional-qZJKBw4W/public/tle
trial=$(mktemp -d "$bench/mirrored-yaw.XXXXXXXX")
module=reports.ALGO08.single-core-2x.mirrored_yaw_trial
python="$release/venv/bin/python"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD:$release/src:$release"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" predict "$archive" "$trial/lock.json" > "$trial/lock.sha256"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" score "$archive" "$trial/lock.json" "$(cat "$trial/lock.sha256")" \
  > "$trial/result.json"
```

Measured causal lock SHA-256 `48b8f1aa2641c8424d3f9d6e05c66b11b83441c691da54a8393663d069be31b0`. [Runner](mirrored_yaw_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_yaw_trial.py)
