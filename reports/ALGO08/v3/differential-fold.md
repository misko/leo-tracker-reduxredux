# A full-aperture differential pilot scout

The shadow receiver missed **10 of 58** weak-carrier factors and **15 of 54** dense DS30 factors. It added four unmatched weak-slice factors. The tested scout falls short of the 20-second acquisition target even with its smaller FFT count, and it loses both primary and residual evidence.

The carrier FFT bound addresses one small stage. The next scout experiment replaces frame covariance, both PCA mode projections, timing search and 24 carrier FFTs per scout with four full-window lag products and a signed phase search. Each antenna supplies independent timing and signed CFO hypotheses. The method uses pilot assets, I/Q, and recorded tuning only. The shadow receiver uses the original full-rate refinement, pilot confirmation, quantized cancellation, exact fractional verifier and causal continuation.

## What 20 seconds requires

The v3 receiver uses 701.1 ms of memory-resident acquisition CPU for 256 DS30-0008 lanes, or 2.739 ms per lane including launch and acquisition administration. Matching that rate over the 13,530 lanes of the full recording estimates 37.05 s. Saving 20 s at that lane count requires 1.478 ms less per lane and leaves 1.260 ms for the whole resident detection and handoff. The measured full warm acquisition took 52.70 s elapsed, including verified input and launch. The exact v3 binary uses 143.1–144.8 ms on the 36 deliberately enriched DS26 weak-carrier lanes, or 3.98–4.02 ms per call. These are separate saved clocks with different work boundaries. [Dense resident prefix](../single-core-2x/receiver-fractional-score-transfer.md) · [Dense lane count](/tmp/leo-algo08v2-2x-bench/exact-curved-0008-stage.json) · [Full warm stage clocks](first-55/stage-clocks.csv) · [Weak native clocks](../single-core-2x/receiver-fractional-absolute-score.md)

| Work in acquisition | Saved measurement and lineage |
|---|---|
| Lag timing and carrier search | 169 and 143 µs per scout on the 72-scout weak sample across six repeats. Same timing object as v3. |
| Modes and full-rate refinement | 321 and 311 µs per scout. Older packed receiver profile, before the later frame-plane improvements. |
| FIR and independent pilot gate | 249 and 101 µs per scout. Older packed receiver profile. The later receiver tiles the FIR. |
| Cancellation and original-sample verification | 0.744 ms per reached cancellation and 0.870 ms per reached verification in the older packed receiver profile. These counts differ from the scout count. |
| Extra CPU for exact fractional scores | Replacing only the verifier adds 0.321 ms per dense lane and about 0.60 ms per weak lane across the corresponding matched measurements. This is a verifier increment. |

The weak timing profile completes 432 scouts. The older packed profile completes 492 scouts, 172 cancellations and 282 verifier calls across 320 lanes. Its clocks establish order of magnitude for the stages without a same-build clock. Even assigning 321 µs to modes and subtracting all timing and carrier search for free on two scouts on every dense lane would project about **17.1 CPU s** of savings. Some lanes take one scout, and the shadow still performs its own search. A scout-only upgrade at this boundary cannot supply 20 s under these measured-rate assumptions. The input, cancellation, coarse refinement and exact verification costs have to enter the same redesign or share the budget with ingress. [Timing profile](../single-core-2x/receiver-spectral-vectors.md) · [Packed scout and verifier lineage](../single-core-2x/receiver-coarse-bank.md) · [V3 target](single-core-target.md)

The earlier four-symbol linear projection covered 7 of 91 reference factors. Its guarded route had to run the original scout on every lane and took 1.45× the native CPU. An earlier 10 ms aperture lost 21 of 128 verified factors, and transferring one antenna's confirmed proposals found no corresponding signed-CFO and timing pair among 141 factors. A raw shortlist missed the phase of seven of 36 factors recovered by the residual scan. These results motivate full-aperture evidence with separate raw and signed-residual proposals on each lane. [Linear projection](../single-core-2x/receiver-projection.md) · [Shortened scout](../single-core-2x/receiver-aperture.md) · [Antenna transfer](../single-core-2x/receiver-lanes.md) · [Raw shortlist](../single-core-2x/receiver-shortlist.md)

## Differential statistic

For each of the four quarter-rate lags, the prototype centers and normalizes each of the original 14 frame rows, then accumulates its lag product across frames. A frame-specific phase cancels in each within-frame product. Correlation against the corresponding centered pilot lag product returns a complex response for each phase. The sum of squared response magnitudes chooses twelve timing hypotheses. The signed CFO search fits the common lag phase rotation over the original carrier bin grid and passes at most four candidates through the original full-rate verifier path. A signed residual gets its own sketch after the normal cancellation step. Two simultaneous pilots contribute cross terms to this statistic, and a mixture can rotate or cancel the true response even when one candidate has a large score.

The model counts eight 4,800-point FFTs per scout, versus sixteen and 24 carrier FFTs in the stock search. That is 77.8% less nominal transform work under an \(N\log_2N\) count. The new scout adds 263,830 within-frame complex products and at most 125,808 direct lag phase products per scout. It still pays for full-window FIR, frame normalization and the causal and exact checks. These counts omit FFT planning, arithmetic outside the stated loops, and all Python overhead.

## Saved signal outcomes

The reference relinks to the released digest `2258f592…`. The instrumentation retained every native factor byte on both slices when the original scout was active. The shifted-lag coverage columns use the original raw or actual signed-residual samples and generously allow seven wrapped native samples and 4.55 kHz at proposal time. The shadow path uses its own measured first carrier for cancellation. The final comparison matches each rank within two wrapped samples and 250 Hz after full-rate refinement and both exact checks.

| Saved slice and scan | Reference factors | Phase supported | Signed proposal supported | Reference factors recovered by shadow | Missing | Unmatched shadow factors |
|---|---:|---:|---:|---:|---:|---:|
| DS26 weak primary | 36 | 34 | 34 | 32 | 4 | 2 |
| DS26 weak residual | 22 | 19 | 17 | 16 | 6 | 2 |
| DS30-0008 dense primary | 33 | 29 | 26 | 26 | 7 | 0 |
| DS30-0008 dense residual | 21 | 15 | 15 | 13 | 8 | 0 |

The phase shortlist omitted 15 of 112 factor phases, even with an oracle CFO. A dense primary miss at visit 14, lane 0, had phase support, a missed signed proposal and an exact/rolled margin of 0.235. A weak residual at DS26-0162 visit 1534, lane 0, missed the timing shortlist despite a margin of 0.159. Both arms yielded zero continued selections on the two short slices. Position impact remains unmeasured.

Thirteen of 48 dense lanes contained a reference factor with both a missed signed proposal and a missed final match. An oracle that always retried just those lanes would already use at least 27% full fallback. Using the matched dense resident cost of 2.739 ms per lane and allowing 1.260 ms total for a 20 s saving, that retry rate leaves at most **0.519 ms per lane** for the new path before charging any other retry. The oracle assumes perfect routing and ignores the actual cost of this NumPy sketch. A production route would need a current-window test with a much lower fallback rate and explicit weak-carrier parity before any timing gate.

A broader acquisition model could build per-frame and per-pilot-block complex matched-filter projections once, then fit two carriers jointly from those projections and their template Gram matrix. It would target the signed residual synthesis and repeated full-rate candidate work as well as proposal search. The tested quadratic fold discards phase information that such a fit needs. The joint model would still have to show that close, weak and initially hidden carriers survive finite candidate support, and quantify differences introduced by the frozen signed rounding and clipping. For a 0.80 ms fast path with a full 2.739 ms retry, the dense timing target permits fewer than 17% retries. That is a budget for a different algorithm, with neither the cost nor the recall established by this experiment.

## Reproduce

The two saved slices are the 18 previously nominated weak stereo visits and the first 24 scheduled dense visits of DS30-0008. The latter uses the authenticated recording reader as the capture account. The count-only experiment runs on CPU 2 inside the shared Gauss lock and stops at continuation. Eight component tests passed across the two carrier experiments.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
main_tree=/home/mouse9911/gits/leo-tracker-reduxredux
work=/var/tmp/leo-algo08v3-differential-fold-new
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 50s \
  sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m tools.pipeline_eval.variants.experimental.receiver_differential_fold \
  "$bench/receiver-fractional-exact-v1" "$work" "$release/assets" \
  "$main_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  "$binding" /srv/bulk > "$work.json"
```

The trace binary SHA-256 is `2179cf38ffdefa545af34ed14ecc4451db0c00b79b0ebb3d25561dd76f9d36fd`. The receipt is `/var/tmp/leo-algo08v3-differential-fold.json`, SHA-256 `2f9cb104300f22ade2c15ce7d47d01278ea34aabc76a3a655e3fc6d9627cc3b2`. It contains the I/Q identities and missed signed proposals.
