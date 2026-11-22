# Resident signed cancellation and cached carrier bins

Resident cancellation and cached carrier bins together saved **3.20%** median paired native CPU on the chronological DS30-0016 prefix after training the compiler at zero and nonzero mixer centers. They reproduced all factors and continuation selections from the floating-FIR, packed phase PGO lead. The original zero-only training saved **3.82%** on that prefix and slowed the nonzero-center stress slice by **7.40%**. Balanced training brought that stress slice back to the lead's CPU time. [Matched timings and manifests](measurements/receiver-resident-and-carrier.json) · [Leading receiver](receiver-phase-packed-pgo.md)

## Feed the signed residual into the resident timing lane

The first timing scout already has a deinterleaved Float32 lane with exact signed CI16 sample values at a zero mixer center. The old path copied the full 1.6 MB stereo window, fitted and subtracted the confirmed pilot on one lane, and converted that lane into the same Float32 timing buffer to start the residual scout. The new path fits against the resident lane and replaces the affected samples in place. It applies the same oscillator recurrence, binary64 block fit, signed clipping and integer rounding. Each block fits before it writes, its sample interval is half-open, and the frame boundary leaves a gap. Consequently a write cannot modify a sample used by a later fit. The second scout sees the same deinterleaved quantized values.

At a nonzero mixer center the existing stereo cancellation and input loader handle the residual. Each antenna retains its own pilot and fit, and the original raw stereo I/Q supplies independent fractional verification. The receiver computes the full residual signal and repeats its full FIR and covariance. The earlier support audit found little reuse in the FIR output intervals. [Support audit](receiver-cancel-support.md) · [Generated source overlay](../../../tools/pipeline_eval/variants/experimental/receiver_resident_cancel.py)

## Cache the original carrier mask

The first and residual scouts both test all 4,096 FFT bins using the same ceiling and floor tests against their signed capture band. The mask depends only on the actual bounds, mixing center, integer scout sample rate, fixed FFT bin count and floating-point environment. The cache key uses the bound and center bit patterns and the scout rate within its workspace. A changed key rebuilds with the original predicate and bin order, including inclusive edge ties and wrapped aliases. Reuse requires nearest rounding. Each entry contains only eligible FFT bin indices and its invocation key. The option is independent of resident cancellation. [Mask kernel](../../../tools/pipeline_eval/variants/experimental/receiver_carrier_eligibility.inc)

## Original zero-center training

Both modules first used the lead's original eight synthetic training windows at their zero mixer center. The three candidates and the lead retained the same floating FIR and guarded frame-relative verifier. Each comparison alternates native call order over lanes and repeats. The physical prefix uses the first 128 scheduled visits, of which 116 pass capture admission on both lanes. Both public geographic simulations use 40 visits each. Austin has four physical edge/window cases and four matched phase nulls, all from one antenna.

| Saved slice | Resident cancellation | Carrier mask | Combined |
| --- | ---: | ---: | ---: |
| DS30-0016 chronological | 2.83% | 0.79% | 3.82% |
| Prospective physical | 2.41% | 0.53% | 3.74% |
| Weak-carrier physical | 3.06% | 0.62% | 3.69% |
| Public northern simulation | 1.94% | −0.52% | 2.90% |
| Public southern simulation | 0.54% | 0.68% | 1.98% |
| Austin field | 2.57% | −1.59% | 5.69% |
| Austin phase nulls | −0.13% | 0.17% | 0.36% |

Each timing is the median paired percentage of full native CPU saved against the lead across five repeats, or nine in Austin. Every build preserved the ordered numerical values and scores of all 396 returned factors, including 124 residuals, on 596 distinct lanes. The 53 retained chronological measurements and all continuation states matched. Acquisition reads, position fitting and rendering fall outside these clocks.

Separate prospective profiles count 492 timing scouts and 172 cancellations over two repeats of 160 lanes. Resident cancellation removes the 172 residual input conversions, lowering the input clock from **61.56 to 48.38 ms** and cancellation from **116.74 to 104.33 ms**. The carrier cache hits on **490 of 492** scouts and reduces the carrier search from **88.34 to 83.10 ms** in its separate profile. The carrier-stage reduction is about 0.53% of whole native CPU. The mode and covariance stage remains around 157 ms of 980 ms native CPU on the same prospective workload.

On the stress slice with alternating ±50 kHz bounds, the resident build took **7.67% more native CPU** with exact factors. The eligibility cache alone was within 0.14% of its matched reference and delivered 108 hits and 36 rebuilds across 144 scouts. The original synthetic compiler training only exercises the zero-center path, so the nonzero path needs a separately trained comparison.

| Full-scan library | SHA-256 |
| --- | --- |
| Frozen floating lead | `dd2d83a8cc865b156115922e057823300e269c2fcb65f525f81e6fa620ed1a20` |
| Resident cancellation | `248294739aba23ba03391ef61dfbb6e2d9cbd20b297f77e986c45c31a9231e69` |
| Carrier-bin cache | `3c599fb6f30c67a2b4513cf8d73171b57dff8d93a768613aec5063429a8413ca` |
| Combined, zero-center training | `3a6a73b601b5587804830209b1a81aedcdc3c0132f92b380d47af94eaaccfbc7` |

## Balanced mixer training

The remedy uses the same eight location-free generated waveforms. Each antenna is evaluated at zero center and again at a signed 100 kHz center, with the sign alternating by generator row. The generated ±225 and ±675 kHz carriers remain within each resulting signed band. The profile contains 16 zero-center and 16 nonzero-center calls. Both the unchanged floating source and the combined candidate are compiled using that exact training order. The evaluation keeps the independently frozen zero-only builds for the direct comparison. [Training and comparison runner](receiver_mixer_profile_trial.py)

| Saved slice | Zero-trained combination vs frozen lead | Balanced combination vs frozen lead | Balanced combination vs balanced reference |
| --- | ---: | ---: | ---: |
| DS30-0016 chronological | 3.40% | 3.20% | 3.54% |
| Alternating ±50 kHz stress bands | −7.40% | 0.02% | 0.19% |
| Public northern simulation | 2.74% | 2.77% | 2.54% |
| Public southern simulation | 1.91% | 1.32% | 1.60% |

The separate three-repeat comparison has identical complete factor and continuation digests in all arms, including scores. The mixed-center replay sets the bounds of the same saved weak-carrier I/Q windows to alternate by 50 kHz in either direction. The offsets belong to this benchmark, and neither production thresholds nor generated training signals use them. The balanced build handles both center regimes with comparable mixed-center cost and keeps the physical gain. The balanced reference SHA-256 is `5953eb6c31d50eb295d356779bb4d0f2732ef169685edee4529ceed392294359`. The balanced combined library is `678d8a24ae727cc65442436955c4e9718354ada4e103db24c362d3d9b727ff9d`.

The prospective profiles put frame covariance through mode construction at about 16% of full native CPU and the complete verifier-input conversion at about 3.3%. The latter converts all 200,000 raw complex samples for each reached verifier. The verifier's integer timing stencils and Lanczos interpolation consume intervals around the confirmed candidate epochs. Sixteen component tests passed, including exact signed residual samples across both lanes and partial blocks, mask boundary and invalidation cases, and the balanced training schedule. [Resident tests](../../../tests/pipeline_eval/test_experimental_receiver_resident_cancel.py) · [Mask tests](../../../tests/pipeline_eval/test_experimental_receiver_carrier_eligibility.py) · [Training schedule test](../../../tests/pipeline_eval/test_receiver_mixer_profile_trial.py)

## Reproduce

Each freeze uses a fresh output directory and writes a binary manifest before scoring. Each command belongs under the same one-core Gauss lock. The physical modes use the release reader under the capture account. The off-site modes accept the earlier authenticated Austin archive and public simulation panel.

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
study="$tree/reports/2026_11_19_receiver_screening"
t=reports/ALGO08/single-core-2x
py="$tree/.venv/bin/python"
assets=/opt/leo-algo08/current/assets
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json
prospective=/srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip
weak="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
panel=/tmp/leo-regional-qZJKBw4W/public/panel.json
austin=/home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip
authority="$study/physical/raw-source-audit.json"
prior="$study/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
resident="$p/resident-copy-rebuild"
eligibility="$p/eligibility-rebuild"
mixed="$p/mixed-train-rebuild"
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
capture() {
  lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="src:.:$t" PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python "$@"
}
lock "$py" "$t/receiver_resident_cancel_trial.py" freeze "$resident" "$assets" \
  "$p/site-free-phase-packed-pgo/float-phase/use.so" > "$resident.json"
lock "$py" "$t/receiver_eligibility_trial.py" freeze "$eligibility" "$assets" \
  "$resident" "$resident.json" > "$eligibility.json"
for trial in receiver_resident_cancel_trial receiver_eligibility_trial; do
  build="$resident"
  if [ "$trial" = receiver_eligibility_trial ]; then build="$eligibility"; fi
  capture "$t/$trial.py" physical "$build" "$build.json" "$assets" "$binding" "$prospective" "$weak"
  lock "$py" "$t/$trial.py" offsite "$build" "$build.json" "$assets" "$panel" "$austin" "$authority" "$prior"
done
lock "$py" "$t/receiver_mixer_profile_trial.py" freeze "$mixed" "$assets" \
  "$eligibility" "$eligibility.json" > "$mixed.json"
capture "$t/receiver_mixer_profile_trial.py" evaluate "$mixed" "$mixed.json" "$assets" "$binding" "$weak" "$panel"
~~~
