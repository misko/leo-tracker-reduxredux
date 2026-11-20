# Complete-epoch short-tap acquisition

The 18-tap proposal visited every original coarse cell and used 30% less median CPU than the installed capture detector. At the same shortlist size as the earlier frame-and-anchor thinning experiment, it covered fewer original peaks, 15/160 versus 19/160. Tripling the shortlist raised coverage to 29/160. The resulting detector matched 14/33 of the installed detector's gate-positive candidates and took 1,054 ms of median host CPU per dual-RX visit, well above the 20 ms target.

[Stage chart PNG](complete-epoch-proxy.png) · [PDF](complete-epoch-proxy.pdf) · [Measured data](qualification.json) · [Evidence hashes](evidence-lock.json) · [Frozen protocol](PROTOCOL.md)

## Matched saved visits

The fixed panel has ten processed visits and one invalid visit across DS26-0036, DS26-0237, DS29-0082 and DS29-0174. It is the earlier thinning panel, reused to keep the peak denominator identical. Both comparison detectors reproduced their prior payload bytes on every admitted visit. The installed capture arm and the proxy share the same calibrated input, fine search, conditioned statistic, fractional refinement and decision gates. The wide arm uses the separately compiled regional detector on the same samples. [Earlier thinning evidence](../../acquisition-support/thinned-capture/qualification.json)

| Measured paired detector | Median CPU (ms) | Median wall (ms) | Wall ≤20 ms | Installed positives matched |
| --- | ---: | ---: | ---: | ---: |
| Installed capture | 1,502.9 | 1,836.7 | 0/20 | 33/33 |
| Complete-epoch 18 taps, cap 96 | 1,053.8 | 1,223.4 | 0/20 | 14/33 |
| Compiled wide | 16.1 | 16.6 | 17/20 | 32/33 |

These are two rotating repetitions per visit on CPU 7, using valid local IQ already in memory. The harness recorded wall and process CPU separately. The wide detector's CPU met 20 ms in all 20 calls. The proxy had 19 missing and four unmatched positives against installed capture. The wide detector had one missing and 15 unmatched positives. Neither excess count identifies ground-truth false positives. Full proxy payloads differed on 20/20 receivers. Final matching allows epoch and CFO aliases with the established two-sample and 1 kHz tolerances.

## Where the proposal lost support

Each acquisition evaluates all 13,333 start times and 21 CFOs using all 15 frame offsets. A default 12-anchor pass retains 216 of 528 template taps. A 22-anchor receiver fallback retains 396 of 968. The tap spans keep each anchor's right edge so that the partial final frame has the original eligibility geometry. This proposal changes the input to the coarse score. The exact folded FFT experiment keeps the entire original template. [Exact folded-bank experiment](../../acquisition-support/folded-bank/README.md)

The 44 measured acquisition invocations covered 12,319,692 short-tap cells and applied the original full score to 550,284 cells in merged ±6-sample intervals. All 367,584 rescored cells exposed by comparable original grids were bit-identical. The paired harness also checked original peak keys and full candidate payloads on the separately screened DS29-0174 implementation. Every original key in the cap-96 scored interior survived the final coarse selection. The coverage loss occurred at nomination. The first-ranked original key survived on 6/20 receivers. The full 96-nomination coverage by recording was 9/48, 9/48, 1/16 and 10/48, in the order above. Cap 32 was a coverage diagnostic on the same ordering.

The median CPU spent per visit was 506.4 ms on the short-tap grid, 97.4 ms on nomination and 108.2 ms on exact rescoring. The measured detector still spent 317.8 ms after excluding the entire coarse stage. Its fractional stage alone had a 121.5 ms median. The largest tracked coarse NumPy buffer footprint was 3.67 MiB. The largest RSS was 246.6 MiB for the paired Python harness, which included all three detectors and the live comparisons.

## Weak, signed and null controls

On one lower-band and one upper-band fixture, all three methods returned a gate-positive candidate matching planted +48 kHz weak and ±720 kHz strong pilots on both receivers within ±2 samples and ±1 kHz unfolded CFO. Empty input and seeded Gaussian noise produced zero gate-positive candidates across all methods in both bands. These small controls show that the proxy can recover a planted pilot. The matched radio visits show that this response does not preserve the ranking needed by the installed detector.

The stage ends at detector output. The selected visits do not form complete positioning inputs. The chart reports detection and timing, with no geographic score for either calibration arm.

## Reproduction

The plot and summary use sealed JSON receipts in the repository and require no radio archive or installed detector.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.complete_epoch_proxy_results \
  --out /home/mouse9911/leo-epochproxy-20261119/reproduced
```

For IQ replay, the selected releases are named in the per-recording receipts. Run `tools.pipeline_eval.qualification.complete_epoch_proxy_eval` with the case ID, on one pinned core, using that release's `src` first on `PYTHONPATH` and the authenticated local recording/former wide-library inputs. The driver checks both the immutable input roster and the source freeze. [DS26-0036 receipt](DS26-0036.json.gz) · [DS26-0237 receipt](DS26-0237.json.gz) · [DS29-0082 receipt](DS29-0082.json.gz) · [DS29-0174 receipt](DS29-0174.json.gz) · [Source freeze](source-lock.json)
