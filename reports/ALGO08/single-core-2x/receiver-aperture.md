# A 10 ms scout inside every 20 ms visit

Shortening only the nomination aperture saved **17.0–17.2% native CPU** across the measured 228 lanes. It missed **21 of 128** reference factors, including **4 of 38** residual-scan factors, and added five unmatched factors. The northern public simulation lost 13 of 25 verified factors. The southern simulation preserved every factor tuple and saved about 13% native CPU. The northern loss and the physical weak-carrier losses reject this fixed aperture for the matched receiver. [Full comparison results](receiver-aperture-results.json)

Earlier short-support experiments used different timing statistics. A three-frame estimator recovered none of sixteen selected original misses, whereas a within-frame differential-pilot method recovered five. The repeat-frame coherence scout needed usable pilot support in both frames of a pair. Neither experiment changed the temporal aperture of the current nonlinear two-mode receiver while preserving both signed cancellation scans. [Earlier differential-pilot comparison](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_19_receiver_screening/acquisition-frontier/README.md) · [Earlier repeat-frame coherence comparison](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_19_receiver_screening/track-recovery/frame-coherence/README.md)

## The aperture and waveform support

The nominal frame rate is 750 Hz, so the first seven frame origins span about 8 ms. The latest of those origins, every candidate within a whole frame period, 128 pilot symbols and the 81-tap FIR support fit inside the first 100,000 native samples. For the quarter-rate scout the last sample touched by the final useful FIR output is index 99,084. This geometry yields a 10 ms prefix with the original full set of timing offsets. It determined the fixed schedule before scoring.

The detector estimates its two principal modes from those seven frames rather than 14. It still uses all eight lag correlations, the same carrier band, 12 timing maxima and four fine proposals. Before signed fine refinement it loads the remaining original native samples. Independent confirmation uses the existing later-symbol or seven-pair gate on the complete 20 ms buffer. Pilot cancellation still computes the full signed residual. The second scout operates on that residual with the same 10 ms aperture, followed by complete signed refinement and the original exact-versus-rolled fractional verifier. Both physical antennas, all eligible visits, and the released per-lane continuation remain in the replay.

Seven nominal origins supply possible pilot opportunities. The scheduling and frame geometry do not guarantee an actual carrier in those origins. A component test plants a real signed pilot wholly in the last 10 ms. The frozen receiver confirms it and the prefix scout misses it. Full-window verification can confirm a late contribution only once some scout nominates the appropriate timing and carrier.

The frozen native profile assigns 117 ms to the quarter-rate FIR and 158 ms to the frame covariance and modes in 1,317 ms total, across its paired repeats. Eliminating both measured stages alone would give an optimistic 1.26× native speedup. Halving FIR work and scaling the quadratic covariance work to seven frames gives an optimistic 1.15× estimate before misses. Timing and carrier FFT sizes stay fixed because the search covers the same phase and CFO grids. Faster times on losing slices can include fewer residual searches and fewer verified factors, in addition to cheaper nomination. [Frozen receiver profile](receiver.md)

## Paired comparison

Matching uses two wrapped samples and 250 Hz signed CFO. Unmatched additions pass the original gates but may be competing signals. They are not established new physical carriers. The lower-margin counts refer to the weaker measured member of a returned two-factor lane. They coincide with missed residual-scan counts in these slices. Both public prefixes are existing simulated development waveforms. The detector never used their position or regional offers.

| Slice | Valid lanes | Reference → short factors | Missed factors | Missed residual factors | Extra factors / residual extras | Lanes with changed exact tuples | Native CPU speedup |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Saved physical prospective | 32 | 33 → 29 | 4 | 0/14 | 0 / 0 | 8 | 1.23–1.24× |
| Saved weak-carrier challenges | 36 | 58 → 55 | 4 | 2/22 | 1 / 1 | 13 | 1.15–1.16× |
| Public northern simulation | 80 | 25 → 16 | 13 | 2/2 | 4 / 1 | 12 | 1.29–1.30× |
| Public southern simulation | 80 | 12 → 12 | 0 | 0/0 | 0 / 0 | 0 | 1.14–1.15× |

The two runs total 0.784 → 0.651 s and 0.784 → 0.649 s native CPU. Neither receiver had enough causal support to select an observation in these sparse saved visits and short public prefixes. The late-only synthetic test and factor comparisons establish a receiver failure. Position and association are outside these clocks.

## Reproduce

The comparison reads the first 16 sorted prospective entries, the 18 previous weak-carrier challenge visits and the first 40 scheduled visits of each public simulation. The two timing repeats rotate native call order across lanes. The 20 ms payload is unchanged in both arms. Run from the repository root using the frozen `107909cc` detector and its pinned assets.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_venv=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_venv" -m "$algo08_native.receiver_build" "$algo08_work/receiver-half-aperture.so" --short-aperture
algo08_lock "$algo08_venv" -m "$algo08_native.receiver_aperture" \
  "$algo08_work/receiver-final-candidate.so" "$algo08_work/receiver-half-aperture.so" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  /tmp/leo-regional-qZJKBw4W/public/panel.json --assets /opt/leo-algo08/current/assets
algo08_lock "$algo08_venv" -m pytest -q tests/pipeline_eval/test_experimental_receiver_aperture.py
```

Both component tests passed. They cover independent accounting of a missed weaker carrier and an extra and the late-half planted pilot.
