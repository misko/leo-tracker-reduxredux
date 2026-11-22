# Conditional 200 m boundary errors under stereo noise

The capture-causal Doppler likelihood selects A at both synthetic locations in both public simulations, even with noiseless observations. On the northern face that would reject the containing alternative. On the southern face it would publish the omission. The exact later-orbit templates distinguish both alternatives with low synthetic error under the same measured receiver-noise controls. The separation is conditional on orbit knowledge and offers no calibrated boundary rule with the available causal predictor. [Per-endpoint scores and orbit authority](measurements/mirrored-noise.json)

The experiment uses two synthetic positions on opposite sides of an intermediate face, with 100 m of clearance per side. The positions are the original public A and B face coordinates from the earlier orbit test. A is west of B at both sites. The face is west-facing in the north, so A represents an omission and B represents a containing offer. It is east-facing in the south, so A represents containment and B represents omission. This geometry labels the synthetic outcomes after scoring. The original paired recordings, retained owners and tangential coordinate are reused from the prior public development checks. [Predeclared protocol](mirrored-noise-protocol.md) · [Noiseless orbit experiment](mirrored-ephemeris.md)

The score compares the squared residuals of the two fixed templates after shared nuisance projection. In the independent Gaussian control, only the noise component along the difference between prediction templates affects the classification. With the exact orbit that decision is optimal for the specified noise and equal priors. The second control preserves the whole measured signed trace within each satellite and enumerates independent sign assignments across satellites. It measures the error of the same template rule under that empirical noise shape. The scores are conditional on the selected associations, common nuisance space and zero-height geometry. Fixed-RF track offsets absorb the fitted calibration column, so the diagnostic applies equally in both calibration gauges.

## Counterfactual error by side

| Public site and templates | Clean classifications, A / B | Gaussian error, A / B | Whole-satellite sign error, A / B |
|---|---|---|---|
| North, causal | A / A | <0.00001% / ≈100% | 0% / 100% |
| North, exact later orbit | A / B | 6.066% / 6.066% | 1.025% / 1.025% |
| South, causal | A / A | <0.00001% / 96.889% | 0% / 99.243% |
| South, exact later orbit | A / B | 3.174% / 3.174% | 0.769% / 0.769% |

The stereo inputs were 224 simultaneous pairs across 12 satellites in the north and 208 across 13 in the south. After clock, track and phase projection, the exact-orbit 200 m template difference was 0.751 and 1.206 Hz RMS respectively. The stereo-average noise proxies were 3.629 and 4.686 Hz RMS. Pooling the epoch pairs yields Gaussian separations of 3.10 and 3.71 standard deviations between their two means. The whole-satellite test evaluates all 4,096 northern and 8,192 southern sign assignments. In these saved traces, their projected score standard deviations were lower than the independent-noise control, at 2.508 and 4.230 Hz versus 3.629 and 4.686 Hz, respectively, along the exact-orbit score direction. [Frozen stereo differences and pairing](measurements/mirrored-noise-lock.json.gz)

Using the causal mean, the true northern B endpoint projects 1,057 m toward A relative to the nominal decision midpoint in equivalent 200 m-template units. The corresponding southern margin is 100 m toward A. These are shifts of the likelihood contrast. They do not estimate the receiver's coordinate error. Adding the stereo-noise proxy rarely reverses that causal bias, while the later orbit restores the expected ±100 m margins by construction.

The stereo difference removes errors common to both receiver paths. The measurements and conditional error rates leave uncertainty from shared clock, waveform, height, owner and orbital errors outside the experiment. The satellite sign calculation uses one recorded shape per satellite and assumes independent, symmetric signs. Its rates describe the enumerated distribution rather than calibrated coverage on actual captures. Earlier causal means, historical orbit weights and held arrival tests also failed to recover both faces. The published India site has a wider membership control and lacks this matched 200 m prediction lock. This experiment closes the fixed nominal likelihood rule for the two mirrored controls without introducing another site threshold. [Causal forecasts](mirrored-causal-forecast.md) · [Orbit weights](mirrored-orbit-weight.md) · [Held arrival](mirrored-arrival.md) · [India wider-offer control](widened-offer-membership.md)

## Reproduce

Run on Gauss with the released public detector files and installed tracking configuration. The first process freezes the receiver noise and support under the previously pinned causal predictions. The second verifies that digest before opening the later generator orbit. Select a fresh output directory for each run.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
trial=$(mktemp -d "$bench/mirrored-noise.XXXXXXXX")
north=("$bench"/covariance-north-inside/baseline/fast-scan-automatic-work/*/detections.json)
south=("$bench"/covariance-south-inside/baseline/fast-scan-automatic-work/*/detections.json)
export PYTHONPATH="$PWD:$release/src:$release"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
module=reports.ALGO08.single-core-2x.mirrored_noise_trial
python="$release/venv/bin/python"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" freeze "${north[0]}" "${south[0]}" \
  "$release/assets/tracks.json" "$trial/lock.json" > "$trial/lock.sha256"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" score "$trial/lock.json" "$(cat "$trial/lock.sha256")" \
  > "$trial/result.json"
```

The stereo lock expands to SHA-256 `5eb89ce0efed15ee545e2a34b4c0cdbc2c354fcddd064d912f3884ecc5390c19`. Both stages used one low-priority Gauss core. [Experiment driver](mirrored_noise_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_noise_trial.py)
