# The effective epoch of the 12 ms primary

An observation-only timing correction explained **75.9% of the squared short-minus-full CFO difference** on the public southern simulation. It explained **1.1%** on dense physical DS30-0008 and increased squared difference by **2.7%** on physical DS30-0016. The physical comparison gives insufficient evidence for changing the short-primary timestamp or for attributing position movement to that timestamp. The southern waveform demonstrates that the aperture shift can matter when RF residuals are small. [Saved audit](measurements/short-primary-epoch-audit.json)

## Source epoch

Both receiver paths export the original start counter and 20 ms recording aperture. The position adapter stamps every lane at **`valid_start_counter + 10 ms`** relative to the common capture clock. `integer_epoch_sample + fractional_epoch_offset_samples` instead gives the selected pilot alignment in its approximately 1.333 ms frame cycle. The adapter uses that epoch for candidate identity checks. The short receiver leaves the original probe start and all sampling metadata intact. [Frequency evidence](../../../src/leo/analysis/glrt_frequency_input.py) · [Factor export](../../../tools/pipeline_eval/qualification/full_v5_check.py) · [Mixed receiver](mixed_aperture_receiver.py)

The checked native sources show that the exported signed CFO is the signed scout/refinement frequency plus the independent fractional verifier's residual bin. The delay-product refinement combines 14 full or eight short origins. The fractional verifier sums per-frame spectra, using 14 or 15 full origins depending on the fractional epoch and support guard, or eight short origins. The 44-sample verifier spacing determines the residual-bin scale. Neither term computes a Doppler derivative or transports its result to the 10 ms metadata instant. The source geometry gives an equal-weight short-minus-full centroid shift near **−4.000 ms** for 14 full origins and **−4.667 ms** for 15. The actual delay products and spectra weight frames by their signals. The equal-weight shift is therefore a prospective correction to test, with no exact effective instant implied for an individual CFO. [Pinned short rebuild](short_signed_trial.py) · [Short primary ABI qualification](mixed-aperture-receiver.md)

## Saved receiver comparison

The audit checked the original terminal, raw authority, detector recipe, probe identity and matching native and owner digests. The two antennas keep the same visit and valid-start metadata in both packets. A same-primary match requires rank zero, pilot alignment within two wrapped samples, and signed CFO within 250 Hz. The full-aperture anchor controls produced exactly zero CFO difference on all **57, 814 and 60** same-primary matches in DS30-0016, DS30-0008 and south respectively. These thresholds isolate identified counterparts from CFO changes that select a different signal. [Trial source](short_primary_epoch_audit.py) · [Previously frozen comparison tolerances](full_short_score.py)

| Recording | Same-primary short lanes | Also same NORAD in both builds and both calibration arms | Bracketed slope witnesses | Stock graph tracks |
|---|---:|---:|---:|---:|
| DS30-0016 | 303 | 92 | 82 | 3 |
| DS30-0008 | 5,092 | 2,978 | 2,453 | 133 |
| Public south | 396 | 226 | 180 | 14 |

Each signed slope was the derivative of a centered quadratic at the target time, fitted to stock CFOs on the same alias-unwrapped graph track and the same published satellite. The fit used at least two and at most six neighboring stock visits on each side within eight seconds, with each nearest bracketing visit within three seconds. The target visit was excluded throughout the slope estimate. The audit applies each source centroid shift to that slope before looking at the short-minus-full signed CFO difference. The existing stock track and satellite labels are retrospective quality filters. The comparison retains correlated observations and uses no surveyed coordinates, position fitting or learned correction coefficient. [Component tests](../../../tests/pipeline_eval/test_short_primary_epoch_audit.py)

| Recording | Observed short-minus-full RMS (Hz) | Predicted RMS / largest absolute (Hz) | Remaining RMS after fixed signed correction (Hz) | Same sign | Squared difference explained |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 70.70 | 12.64 / 15.23 | 71.66 | 52.4% | −2.7% |
| DS30-0008 | 70.84 | 14.25 / 20.47 | 70.45 | 56.5% | 1.1% |
| Public south | 10.68 | 10.78 / 16.20 | 5.24 | 91.7% | 75.9% |

Reversing the correction sign yields RMS of 71.98, 74.01 and 20.81 Hz in the same order. The largest predicted physical timing component was **20.47 Hz** in these supported samples. It is an empirical maximum under the stated slope and centroid model. The stock physical RF RMS was **109.38/109.48 Hz** on DS30-0016 and **129.70/129.66 Hz** on DS30-0008 for fixed-zero/fitted `c`. Southern stock RF RMS was only **6.50/6.39 Hz**. The paired published position separation was **1.055/0.968 km** on DS30-0016, **1.088/1.057 km** on DS30-0008 and **0.369/0.921 km** in south. Each separation combines the original detector, graph and solver changes. An RF-only correction on selected saved observations places no bound on the resulting location without a matched position fit and its geometry. No replacement locations were estimated. [Physical raw pair](full-short-physical.md) · [Southern transfer](full-short-transfer.md) · [Sealed timestamps and both calibration arms](measurements/short-primary-epoch-audit.json)

## Reproduction

The script uses the already sealed DS30-0016 physical pair, southern publications and DS30-0008 candidate and stock publication. The receiver source hashes bind the reviewed C sources that produced the existing binaries. The test computes stock graph tracks and CFO summaries only. Each run used the low-priority Gauss slot with one numerical thread.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/src:$PWD" OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 45 "$release/venv/bin/python" -BPs reports/ALGO08/v3/short_primary_epoch_audit.py \
  /var/tmp/short-primary-epoch-reproduction.json --track-config "$release/assets/tracks.json"
```
