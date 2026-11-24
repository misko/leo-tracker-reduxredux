# Full-aperture timing rescue of 8 ms detections

Adding an independent differential full-aperture scout to the measured 8 ms shortlist leaves **3 of 9 dense and 2 of 8 weak uncovered 20 ms primary peaks**, even granting correct signed carrier and free exact confirmation wherever timing is supported. The first four original full-window timing rows cover all 17 at the same loose tolerance. Generating those four rows still takes the original full-window timing calculation. The cheaper scout fails the retained-evidence gate, and the saved clocks leave little room to pay for rescue on top of a complete short receiver. [Frozen scope](two-aperture-timing-replay-protocol.md) · [Sealed replay](measurements/two-aperture-timing-replay.json)

## Independent timing support

The replay joined enrollees by authentic sample digest, original clip or visit, antenna and tuning edge. The dense join also checks hardware counter and RF center. The older weak short receipt lacks separate counter and RF fields. The dense slice uses the scheduled nonanchor lanes in the first 24 DS30-0008 visits. The weak slice is the existing 18 stereo DS26 challenge clips, forced short. The detailed receipt lists the eligible 20 ms rank-zero positives, their corresponding short outcomes, and their sample identities. No equivalent South timing ledger was used.

| Saved comparison | Dense | Weak |
|---|---:|---:|
| Joined lanes | 32 | 36 |
| Full 20 ms primary positives | 24 | 36 |
| Short factor already matching full within ±2 wrapped samples and ±250 Hz signed CFO | 15 | 28 |
| Full primary unmatched by the short factor | 9 | 8 |
| Unmatched peaks covered by short seed or independent differential timing, ±7 native samples | 6 / 9 | 6 / 8 |
| Unmatched peaks covered by short seed or first four ordinary full timing rows, ±7 native samples | 9 / 9 | 8 / 8 |
| Differential scout has a signed seed on unmatched peaks, ±7 samples and ±4.55 kHz | 4 / 9 | 6 / 8 |
| Differential timing covers short-empty, full-positive peaks | 3 / 5 | 1 / 2 |

One measured short factor contributes at most one seed. The independent branch uses the previously executed full-aperture differential scout, with all 14 frames, four lag-product correlations and its original twelve ordered timing picks. A separate control uses the first four raw phase peaks from the original full-window scout, before carrier search. The timing union is a generous test of the predeclared phase tolerance. A row within ±7 samples may fail carrier search, refinement or the original acceptance gates. Peaks outside that tolerance would require an expanded or different measurement and its cost. The archived differential receiver's own verified full run lost 7 of 33 dense and 4 of 36 weak reference primaries and also missed signed residual factors. There was no new receiver run here. [Differential fold](differential-fold.md) · [Ordinary timing trace](timing-only-oracle.md) · [Short receipt](eight-ms-primary.md)

## Paid acquisition boundary

The physical DS30-0049 six-member factorial measured 724 native lane calls at each aperture. All rows below charge its 92 two-scan anchors once and leave 632 nonanchor lanes. These are sums of actual native callback clocks on the named lanes. The concatenated rows assume the exact earlier measured clock for each selected retry and omit any added discovery, dispatch, or long measurement of already-matching short positives. They have no process-level timing interpretation.

| Nonanchor path | Native CPU | Native callback wall |
|---|---:|---:|
| Original full 20 ms two scans | 1.599 s | 1.603 s |
| Full 20 ms primary | 1.259 s | 1.264 s |
| 8 ms primary | 0.756 s | 0.759 s |
| 8 ms + 20 ms primary retry on all 424 short-empty lanes | 1.386 s | 1.392 s |
| 8 ms + answer-key retry on only the 55 recoverable empty lanes | 0.880 s | 0.885 s |
| 8 ms + answer-key retry on all 83 unmatched full primary peaks | 0.943 s | 0.948 s |

Before any long measurement the 8 ms path leaves **0.503 s**, or **796 µs per nonanchor**, against direct 20 ms primary. Keeping every short callback and retrying on every short-empty lane spends **0.127 s more** than direct full primary and ignores displaced positives. Perfect knowledge of all 83 unmatched primaries would leave **0.316 s**, or **501 µs per nonanchor**, for all discovery and for any 20 ms measurements on retained short positives. In the first 384 visits full primary recovered six of the seven installed-owned empty losses in each calibration arm. The seventh required the original cancellation scan in the factorial. The 20 ms primary budget therefore describes only the primary part of the recovery goal. Adding work after every paid short callback also leaves no speed budget versus short alone. [Physical factorial and both calibration arms](ds30-0049-receiver-factorial.md)

## Which work is shared

The first five normalized frame planes, their 15 pre-eigensolve covariance entries, and the first 19,990 quarter-rate FIR results survive the aperture change. Full 20 ms requires 14 planes and 105 covariance entries. The expanded covariance changes the two projected modes even over the shared prefix. Each lag product then involves new old-frame weights as well as cross-products between early and late frames. The old covariance and the short projected lag spectra do not determine these shifted products. Reusing them would require a new basis of frame-pair correlations or recomputing the projected streams. The template and FFT plans already persist in the receiver. The signed residual scan starts with new quantized samples from the selected full primary, so original two-scan parity needs its own search and signed cancellation. [Existing exact state ledger](resumable-primary-ceiling.md) · [Native frame projection](../../../tools/pipeline_eval/variants/experimental/receiver_frame_planes.inc)

Earlier short nomination with full 20 ms verification lost 21 of 128 factors and 13 of 25 on the North slice. The measured late periodicity cue restored zero of the seven 0049 owned empty losses at its frozen quota. The directed tail verifier needs a candidate that already exists. A sparse template retaining 16 frequency lines preserved about 3.6% of template energy in the earlier bound. The four-row oracle skips timing discovery and reduces carrier search while still paying modes, refinement and confirmation. Its separate two-scan receipt supplies no measured 0049 marginal saving. [Short nomination](../single-core-2x/receiver-aperture.md) · [Late rescue](late-pilot-rescue.md) · [Tail confirmation](tail-confirm.md) · [Sparse template](sparse-template.md) · [Timing oracle](timing-only-oracle.md)

The earlier three-aperture union matched 35 of 43 dense reference factors with perfect hindsight and three already computed detector calls. The survey saved work by skipping channels and missed the geographic error gate on dense and fixed-zero South. Neither supplies independent full-window evidence to each admitted lane at the required cost. [Aperture union](aperture-factor-union.md) · [Channel survey](survey-channels.md)

Stop at the saved replay. Advancing this design would require an independently measured full-aperture statistic that covers the lost phases under the remaining CPU budget, plus a bounded signed carrier and cancellation path. The current replay opened no I/Q, ran no native callback or position fit, and used no Gauss lease.

```sh
python -m reports.ALGO08.v3.two_aperture_timing_replay /tmp/two-aperture-timing-replay.json
python -m pytest -q tests/pipeline_eval/test_two_aperture_timing_replay.py
```
