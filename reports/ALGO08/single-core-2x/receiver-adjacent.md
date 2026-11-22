# Full-rate adjacent-symbol timing on the raw and residual scans

Using the historical adjacent-symbol contrast as the only timing scout increased native receiver CPU by **33%** and missed **39 of 128** frozen reference factors, including **19 of 38** second-scan factors. Those figures cover 228 lanes in two matched repeats. Running the original timing scout whenever the adjacent proposals failed the existing signed confirmation increased CPU by **71%** and still missed **5 factors**, including **4 second-scan factors**. [Per-visit factors, counts and clocks](receiver-adjacent-results.json)

## What changed

The historical wide GLRT trial supplied the first positive adjacent-symbol peak as an additional hint. It recovered 5 of 16 selected old misses and 2 of 8 disjoint misses. Its independent FFTW score took a median 5.78–6.17 ms CPU per stereo visit on 32 saved visits. The history reviewed contained no use of this statistic as the sole phase scout for the raw and signed residual scans of the current receiver. The current nonlinear scout combines eight quarter-rate timing lags in two principal modes. The earlier four-symbol projection trial used linear correlations. [Historical differential results](../../2026_11_19_receiver_screening/acquisition-frontier/README.md) · [Historical FFTW implementation](../../2026_11_19_receiver_screening/acquisition-frontier/differential-runtime/README.md) · [Linear projection study](receiver-projection.md)

The trial uses the historical FFTW score across each complete 200,000-sample lane at 10 MS/s. For a single carrier, the product of a sample and the conjugate of the sample 44 samples earlier contains a fixed CFO-induced phase. Taking the squared magnitude of the differential correlation removes that common phase. The score uses the existing three fractional frame-start classes at 0 and ±⅓ sample and subtracts the energy-normalized rolled-control score from the energy-normalized exact-pilot score. Cross terms between two carriers remain in these products. The second pass forms its own adjacent products from the actual signed quantized residual after pilot subtraction.

Each pass supplies up to the frozen budget of 12 positive local maxima, with the historical separation of five wrapped native samples. The quarter-rate mode and carrier search still choose signed CFO proposals. Timing proposals map to the nearest quarter-rate sample for that search, while the full-rate signed refinement uses the original native epochs. The existing coarse confirmation, full signed pilot cancellation, independent fractional verification and duplicate veto operate on the same waveform buffers as in the frozen detector. Both antennas and all eligible visits are evaluated independently. The experiment uses the waveform, the two pilot references and the original RF metadata for signed search bounds.

The fallback arm repeats the original nonlinear timing search on a pass only when every adjacent proposal fails the signed confirmation in that pass. Signed confirmation precedes the later fractional gate, and a different confirmed candidate can prevent fallback. For example, on the prospective visit `DS26-0036-v0376-rx1` physical lane 0, both arms confirm the same −223.826 kHz primary. The fallback arm retains a verified −315.967 kHz residual in place of the frozen receiver’s −65.408 kHz residual. The latter never reaches the fractional verifier in that arm. [Changed lane tuples](receiver-adjacent-results.json)

## Paired comparison

The CPU ratios below divide variant CPU by frozen receiver CPU in each of the two repeats. Factor matching uses wrapped timing within two samples and signed CFO within 250 Hz. An extra is a gate-passing output without a matched frozen factor. These bounded comparisons measure agreement, with no independent physical truth labels for the extras. The two simulated prefixes are public development waveforms.

| Slice | Lanes | Frozen factors / residuals | Primary misses / residual misses / extras | Fallback misses / residual misses / extras | Primary CPU ratio | Fallback CPU ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Saved physical prospective | 32 | 33 / 14 | 12 / 8 / 1 | 1 / 1 / 1 | 1.24× | 1.63–1.64× |
| Saved weak-carrier challenges | 36 | 58 / 22 | 14 / 9 / 2 | 1 / 1 / 2 | 1.25× | 1.49–1.52× |
| Public northern simulation | 80 | 25 / 2 | 13 / 2 / 6 | 3 / 2 / 7 | 1.33–1.34× | 1.81–1.83× |
| Public southern simulation | 80 | 12 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1.48–1.51× | 1.86–1.87× |
| All four slices | 228 | 128 / 38 | 39 / 19 / 9 | 5 / 4 / 10 | 1.33× | 1.71× |

Mean total CPU per repeat was 0.8233 s frozen, 1.0975 s adjacent-primary and 1.4098 s with fallback. The fallback arm reran the nonlinear search on 150 of 228 first passes and 46 of 96 attempted residual passes. The primary arm changed exact factor tuples on 40 lanes. The fallback arm changed tuples on 13 lanes, including two weak-slice lanes where it matched both carriers within the evaluation tolerances. The southern slice matched every factor tuple. At 1.48–1.51× native CPU there, the full-rate scout costs more even with matched outputs. These native timings cover cancellation and verification, with FFT plans and template references prepared before the timed calls. The study leaves publication and position accuracy unmeasured.

## Reproduce

The trial reads the first 16 sorted prospective archive entries, the 18 saved weak challenges and up to the first 40 scheduled visits of each public simulation. It rotates call order over both lanes and both repeats and records the source I/Q hashes. It uses the existing exact experimental `107909cc` detector as reference. The opt-in build of the alternate scout was `8d13765a0d0a1c7959fa19581c3aab34058b8fac00e5eaf4ce3056c3126ded5c`.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_venv=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_venv" -m "$algo08_native.receiver_build" \
  "$algo08_work/receiver-adjacent-ranked.so" --adjacent-primary
algo08_lock "$algo08_venv" -m "$algo08_native.receiver_adjacent" \
  "$algo08_work/receiver-final-candidate.so" "$algo08_work/receiver-adjacent-ranked.so" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  /tmp/leo-regional-qZJKBw4W/public/panel.json --assets /opt/leo-algo08/current/assets
algo08_lock "$algo08_venv" -m pytest -q tests/pipeline_eval/test_experimental_receiver_adjacent.py
```

Both component tests passed. They check the historical score surface and its phase ranking, lane independence, and signed confirmation and fallback through full cancellation and verification on a planted pair. Both detector builds reproduced their recorded hashes.
