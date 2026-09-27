# Known-channel native GLRT prototype

## Result

Reusing a causal channel state removes the blind 120 ms screen, timing
acquisition, and full-CFO search. The stable V1 port scores one selected 20 ms
interval at caller-supplied fractional timing and CFO with the existing final
exact/rolled-control GLRT, then returns a fresh CFO innovation. It includes no
lookahead and does not claim to refit timing: fast results are labelled
`predicted_verified` and `timing_bracket_status=not_searched`.

V2 accepts a natural non-contiguous `raw[:, rx, :]` view, so Python does not
pack one receiver first. It also converts only the sample intervals read by the
final GLRT. At `frame_limit=16`, V2 is bit-identical to V1 for integer,
fractional, and physical-period-wrap timing cases.

| Rate / path | Full Python call wall, median | Same-library blind | Ratio |
| --- | ---: | ---: | ---: |
| 2.5M, V1 full aperture | 0.308 ms | 1.536 ms | 4.99x |
| 2.5M, V2 full aperture | 0.173 ms | 1.536 ms | 8.89x |
| 2.5M, V2 partial 4 frames | 0.0545 ms | 1.536 ms | 28.2x |
| 2.5M, V2 partial 2 frames | 0.0392 ms | 1.536 ms | 39.2x |
| 5M, V1 full aperture | 0.597 ms | 3.227 ms | 5.40x |
| 5M, V2 full aperture | 0.321 ms | 3.227 ms | 10.1x |
| 5M, V2 partial 4 frames | 0.0928 ms | 3.227 ms | 34.8x |
| 5M, V2 partial 2 frames | 0.0598 ms | 3.227 ms | 54.0x |

These are 300-repetition x86 synthetic timings with warmed workspaces. Both
baseline and candidate come from the same V2 shared object and use the newer
decision-band scientific flags. Blind timing includes the natural dual-RX view
materialization performed by its existing binding. Server timing does not
establish ARM timing.

The partial paths run the unchanged final GLRT statistic over the first 4 or 2
supporting frames. They explicitly report `partial_N_frame_final_glrt_unqualified`,
the requested frame limit, used support, and full available support. They are
different statistics from the full-aperture score. At a 6.25% blind-acquisition
fraction, the synthetic per-hit ratios imply illustrative aggregate ratios of
10.4x/11.2x for partial-4 and 11.6x/12.5x for partial-2 at 2.5M/5M. This
arithmetic is not a causal replay result; expiry and failed innovations can
raise acquisition frequency.

## Interface

```python
from known_state_v2 import NativeKnownStateV2, build_library_v2

library = build_library_v2()
with NativeKnownStateV2(rate_hz, edge, library) as detector:
    result = detector.measure(
        raw_20ms[:, receiver, :],
        predicted_epoch_samples,
        predicted_cfo_hz,
        frame_limit=16,
    )
```

The result includes canonical physical-750-Hz `epoch_samples`,
`tracking_cfo_hz`, unclamped `cfo_innovation_hz`, exact/control/margin,
support counts, converted sample count, source stride, validity, reacquisition
status, score/timing semantics, and conversion/kernel/total CPU and wall time.
CFO innovation above 8 kHz requests reacquisition; it is never clamped into the
trust bound. Optional local timing recovery evaluates a +/-1-sample bracket and
is much more expensive, so it is an exception path rather than a cache-hit
operation.

Timing normalization uses the physical period `rate / 750.0`, not rounded
template length. Tests cover equivalent 2.5M phases `3333.1` and `-0.233...`,
equivalent 5M phases `6666.6` and `-0.066...`, and negative wrapping.

V3 separates the acquisition/scoring CFO from the expected physical CFO while
leaving the V1 and V2 contracts and binaries unchanged:

```python
from known_state_v3 import NativeKnownStateV3, build_library_v3

library = build_library_v3()
with NativeKnownStateV3(rate_hz, edge, library) as detector:
    result = detector.measure(
        raw_20ms[:, receiver, :],
        predicted_epoch_samples,
        scored_cfo_hz=state.scoring_cfo_hz,
        expected_physical_cfo_hz=state.cfo_hz,
        frame_limit=16,
    )
```

The unchanged GLRT scores at `scored_cfo_hz` and reports its unclamped residual
as `cfo_residual_from_scored_hz`. V3 derives measured physical CFO as scoring
center plus that residual. Only `physical_cfo_innovation_hz`, measured physical
CFO minus the caller's expected physical CFO, is checked against the 8 kHz
reacquisition threshold. Omitting `expected_physical_cfo_hz` defaults it to the
scoring center and exactly preserves V2 reacquisition behavior. The inherited
GLRT limits its scoring center to +/-400 kHz; physical CFO may cross that bound
as long as expected minus scored CFO fits its +/-half-symbol-rate residual
support.

V4 adds exact-equivalent strided ingress for the blind fallback:

```python
from blind_strided_v4 import NativeStridedBlindV4, build_library_v4

library = build_library_v4()
with NativeStridedBlindV4(rate_hz, edge, library, bins=512) as detector:
    result = detector.run(raw_120ms[:, receiver, :], maximum=1, seeded=False)
```

Rank folding reads the natural receiver stride directly. V4 packs only each
selected 20 ms interval before invoking the unchanged confirmation API. It
preserves every rank, screen, epoch, nuisance, candidate, score, support flag,
and mask; its timing fields intentionally measure the new path. The scalar
stride-4 fold is source-bounds safe on ARM. Restoring NEON requires an ABI that
supplies the sample-aligned raw base and receiver lane, followed by separate
ARM qualification.

The server cost profile attributed 38--40% of the outer blind call to the
Python/NumPy receiver pack. Perfect removal therefore has only a 1.62--1.67x
server ceiling, and native DSP would still need about 6x less work to reach
10x. This is a server harness result. It does not show that the production ARM
pipeline performs the same copy or would receive the same benefit.

The clean chronological development replay measured 1.477x total CPU and wall
speedups across 256 receiver-visits: 1.567x at 2.5 MS/s and 1.435x at 5 MS/s.
All 240 blind-fallback scientific result structures matched the common-profile
baseline exactly, all 36 reference positives were retained, and 16 visits used
the cache. Three additional positive cases remain unadjudicated because the
real observations have no truth labels. This development result does not
authorize a holdout claim. It shows that strided ingress is useful server
cleanup and that it cannot deliver the requested 10x overall improvement.

V5 is a separate ARM-oriented prototype. Its ABI receives the sample-aligned
dual-RX base and an explicit receiver lane instead of a shifted receiver view:

```python
from blind_aligned_v5 import NativeAlignedBlindV5, build_library_v5

library = build_library_v5()
with NativeAlignedBlindV5(rate_hz, edge, library, bins=512) as detector:
    result = detector.run(raw_120ms, receiver, maximum=1, seeded=False)
```

Each NEON `vld4.16` begins at RX0 I on a real sample boundary. The two loads in
a four-cell lag group consume samples `k..k+3` and `k+4..k+7`; the existing
fold validity condition proves the latter remains inside the selected 20 ms
window. The helper selects lanes 0/1 for RX0 or 2/3 for RX1, widens every CI16
product before addition, and retains exact int64 accumulation.

Host tests match V4 field-for-field for both rates, receivers, seeded modes,
all six confirmations, all screen rows, multires timing, and CI16 extrema. A
Cortex-A9 `arm-none-eabi-gcc` cross-build of the exact helper verifies generated
`vld4.16`, `vmull.s16`, `vmovl.s32`, `vadd.i64`, `vsub.i64`, and `vst1.64`
instructions. The object was disassembled only. It was not run or timed on ARM,
so V5 carries no ARM speed or deployment claim.

## Bounded quality evidence

The supported 2.5/5M constructed controls provide eight receiver cases per
kind. Full, partial-4, and partial-2 each gated 8/8 truth-seeded pilots and 0/8
noise plus 0/8 tones under the strict margin and trusted-CFO rule. Each negative
received one deterministic stale-state-like timing/window/CFO challenge. These
small controls are not calibrated classifier rates.

A separate same-visit oracle microbenchmark used the common-profile blind
candidate from seven development receivers. This is deliberately labelled
noncausal. Full and partial-4 retained strict margin plus trusted CFO on 6/7;
partial-2 also retained 6/7. The seventh reference positive was marginal
(`margin=0.0273`) and its acquired-to-tracking CFO shift was about 98.5 kHz.
V2 incorrectly reused its physical tracking CFO as the next GLRT scoring
center, reducing the full margin to 0.0047. This is a lost cache hit that must
be charged as fallback cost, not an acceptable retention exclusion. Median V2
CPU was 0.163 ms full, 0.0485 ms partial-4, and 0.0277 ms partial-2.

The V3 dev-only same-visit oracle check scores at each blind candidate's
acquisition CFO and compares measured physical CFO with the candidate's
tracking CFO. It retains 7/7 reference positives at full, partial-4, and
partial-2 apertures. For the previously lost candidate, full V3 reproduces the
blind exact score `0.069553`, control `0.042269`, and margin `0.027284`; its raw
residual from the 103.754 kHz scoring center is -98.544 kHz, while its physical
innovation against the expected 5.210 kHz state is exactly zero. This evidence
is noncausal and cannot establish prospective retention.

Twenty-four unit tests cover pilot scoring, input preservation, local recovery,
wrong timing, wrong CFO, noise, tone, source bounds, physical-period wrapping,
V1/V2 full-score identity, natural dual-RX stride, explicit partial support,
dual-CFO acceptance, default V2 compatibility, stale physical state, physical
CFO beyond the scoring bound, GLRT residual-support bounds, both blind rates
and receivers, all six confirmations, seeded and unseeded paths, every screen
row, CI16 extrema, the aligned dual-RX layout, and multires V5 equivalence.
Root owns the prospective cache state and chronological replay needed to decide
whether real hit rate and expiry behavior can deliver a 10x aggregate gain.

## Receipts

- V1 library: `dac8d5c4ccc03e36a8182646f561caf7866a61b895b1a3a21a4a73038b9c06b1`
- V1 build receipt: `eaeab3807c958bd89309c5957478042b4b2875702626fb98b0efc2e3d072ffdc`
- V2 library: `7b0bfc23d530627896aa8be10bcf96d93cd2c256f8cc00960df27fc2935534d2`
- V2 build receipt: `80bdeb0c9e4fe7db7945fc6ffa20f9074ee8dcf4fbffaa45a2719777a5205e7b`
- Synthetic V2 benchmark: `3786782ee480f4982e28c01fc5e74e0f92c9fd3c77102a41524362c77c90d384`
- Constructed controls: `b9c8431900857923cc4b8705c235d1bd1ec294066d4f98621853041098fc3e20`
- Real oracle qualification: `f1bde81e0b23122d5b735f878f6882f194e3d73870ed55caadc1d097215b8ea8`
- V3 library: `8250b58f6619ca63f2340c5f34e5dee893acc7cebc2946029f76df8395be323b`
- V3 build receipt: `888f6a55ba1356a9966cc1d8fad35578cd46b93cc715c7533bba5b7a1082b328`
- V3 dual-CFO oracle qualification: `9d0aef066bd9e8cde80d841c1776d09b39af793da305ae3eeafb4c91c7a76bbf`
- V4 strided-blind library: `8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614`
- V4 build receipt: `5103c6ebfde2a95e0ecdeec3c2e5c5c3253cf04aaca15da2fda1b5b6c0d1ee3e`
- V4 final development replay: `e2528d2a77d4818945c273db77272eb5e8d69f258e2ae664ecda1f3870a82d63`
- V5 aligned dual-RX library: `61005d86d0b4dad8f03b56951e20ec6f360280f6f2b94e70450c403105d6ac67`
- V5 build receipt: `0ddc880b77a17f6a25c0da32400d48beba96feede69abdec20a5c0b9e136ce4c`
- V5 Cortex-A9 cross-check: `f355c06ff1d392043237c0c5a58fd4153843eeccf1b9b42b7763311cf1903268`
