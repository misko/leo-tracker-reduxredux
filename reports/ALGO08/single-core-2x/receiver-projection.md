# Reusing pilot projections after signed cancellation

The unguarded scout recovered **7/91** verified factors on the two saved slices. The guarded scout matched the exact receiver on all 68 lanes and required a full fallback on all 68. It used **1.45× as much native CPU** as the exact receiver. Fixing the first proposal and cancellation to the exact receiver still recovered only **2/36** residual seeds. This bank leaves too little independent evidence to replace the full scout. [Per-slice seed, factor and CPU receipts](receiver-projection-results.json)

This experiment replaces each lane's frame covariance and differential timing search with a linear ambiguity bank. Every measured carrier still requires the independent pilot confirmation and the exact versus rolled-control fractional verifier on the original I/Q. The design processes both physical antennas separately and uses the recorded RF bounds and the selected pilot edge. The benchmark never uses orbital information, station truth, or position outcomes. [Reason for testing a lane-local bank](receiver-lanes.md)

The prototype uses four pilot symbols on quarter-rate I/Q from two separate frames. For each 50 kHz carrier hypothesis spanning the signed 1.6 MHz acquisition band, it correlates the short template at every allowed frame phase. It keeps twelve distinct timing maxima and uses the existing lane-specific frequency search and native refinement for up to four seeds. The two-frame choice keeps the projection bank small and retains independent per-visit signal evidence.

On the first pass the detector retains the two forward I/Q spectra and the decimated sample vector. On the residual pass it convolves the signed integer correction, calculated as the original ADC values minus the actual quantized residual values produced by the existing cancellation kernel. Subtracting the correction spectra from the cached spectra gives the residual projections by linearity. This includes any quantization and clipping in the actual cancellation. Float32 arithmetic can round differently from direct remeasurement. The final timing gate reads the actual residual and the fractional verifier reads untouched input in both passes.

## Safe fallback

For any overlooked pilot vector, the Cauchy–Schwarz upper bound on normalized coherent power in nonzero I/Q is one. The short aperture leaves unscored symbols and coarse carrier cells, so that generic bound cannot exclude the released fractional margin threshold of 0.025 or certify the independent frame-group ranking. An all-zero physical lane has zero correlation and ties every bin, which the released pilot gate rejects. The guarded trial therefore takes the full released path for every nonzero unresolved lane. It runs the proposed bank first so the timing includes the attempted optimization and the actual fallback.

The trial compares independent projection, guarded projection, and a diagnostic with the exact receiver's first proposal and cancellation. The diagnostic uses the same actual signed correction as the exact first scan, so a failed raw shortlist cannot prevent inspection of the new residual scout. It is outside the proposed operating route.

## Seed and factor outcomes

Seed recall requires a proposal within two wrapped samples and 1 kHz signed CFO of the matching exact reference factor, measured separately for each cancellation pass. Final factors are paired within two samples and 250 Hz. The independent projection had only seven residual scans because its first scout rarely confirmed. The exact-first diagnostic then evaluated 55 residual scans with the exact first proposal. One independently returned factor matches an exact receiver residual factor despite lacking a pass-specific seed match. Refinement and pass order can differ between the two receivers. The two exact-first residual matches passed the original gates.

| Measure | Ordinary slice, 32 lanes | Weak-carrier slice, 36 lanes |
| --- | ---: | ---: |
| First-pass seeds matching reference factors | 3/19 | 3/36 |
| Independent second-pass seeds matching reference factors | 0/14 | 0/22 |
| Second-pass seeds matching reference factors after exact first cancellation | 0/14 | 2/22 |
| Returned factors matching the exact receiver | 3/33 | 4/58 |
| Guarded fallback lanes | 32/32 | 36/36 |
| Frozen exact native CPU, two repeats (s) | 0.138–0.140 | 0.211–0.213 |
| Unguarded native CPU, two repeats (s) | 0.078–0.079 | 0.0927–0.0934 |
| Guarded native CPU, two repeats (s) | 0.210–0.212 | 0.295–0.298 |

The cost of the unguarded route reflects the many omitted residual searches and verifies. The fallback rate is an observed isolation result with the stated conservative bound. The four-symbol aperture discards much of the published pilot's discriminating support. Using more symbols would require a denser carrier grid for this direct implementation. Reusing the forward data spectra leaves the inverse transforms across hypotheses in place. A higher-recall linear scout would first need a cheaper full-band, all-phase projection with enough waveform support to establish a selective bound. [Frozen scout profile](receiver.md)

Two component tests passed. They check wrapped phase and signed seed accounting, a silent partner, execution of the actual signed-correction residual on a planted pair, and exact fallback results.

## Reproduce

Use the frozen faster comparator, SHA-256 `107909cc17e994950f7ffb2dce215114959565d5874122d958a6480132c242a5`. Run from the repository root. Archive entries are verified before capture data enter the native timing clock. For the first archive, the first 16 entries sorted by recording and visit are fixed by the script. The second uses the 18 previously nominated weak/challenge visits. Two repeats rotate arm order. The separate stage diagnostic uses the same bytes.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_venv=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_venv" -m "$algo08_native.receiver_build" "$algo08_work/receiver-projection.so" --projection
algo08_lock "$algo08_venv" -m "$algo08_native.receiver_projection" \
  "$algo08_work/receiver-final-candidate.so" "$algo08_work/receiver-projection.so" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  --assets /opt/leo-algo08/current/assets
algo08_lock "$algo08_venv" -m pytest -q tests/pipeline_eval/test_experimental_receiver_projection.py
```
