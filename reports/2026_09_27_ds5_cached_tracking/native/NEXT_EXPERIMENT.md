# Next experiment: reuse differential phase for blind CFO acquisition

## Decision from the existing receipts

Do not make receiver-to-receiver seeding the next experiment. The fixed
development receipt contains 128 physical visits and 256 receiver-visits. When
paired by physical visit, 94 visits have no reference-positive receiver, 32
have exactly one, and only two have both. The 36 receiver-positive total is
therefore concentrated in different visits or one receiver.

With receiver 0 processed first, it is positive on 27 visits and receiver 1 is
positive on nine. Only two of those nine receiver-1 positives have a concurrent
receiver-0 positive. In both, the fitted frame phases are close (0.125 and
0.310 microseconds circular error), but their physical CFO differences are
456,141 and 228,603 Hz. Their scoring-CFO differences are 568,002 and 327,147
Hz. None satisfies the 8 kHz identity threshold. A constant inter-receiver CFO
offset is also contradicted by those two offsets, and two paired examples are
insufficient to fit a channel-dependent transform.

The other receiver's candidate timing is within two microseconds for 19 of 27
receiver-0 positives, but this does not save service: receiver 0 was processed
first, and the second receiver was reference-positive in only two of those
visits. A seeded miss on the second receiver must still fall back to its own
blind search because a reference-negative result is not evidence of physical
absence. Direct RX seeding can therefore avoid at most part of two blind calls
in this ordering, while adding an attempted seed before many fallbacks.

Even an impossible zero-cost oracle for all 36 positive receiver-visits, with
ordinary blind processing for the other 220, has an all-visits ceiling of
`256 / 220 = 1.164x`. The rank, nuisance, coarse timing, fine CFO, and final
confirmation statistics depend on each receiver's fresh samples; a result from
one receiver cannot replace those measurements on the other. Static templates,
FFT plans, and twiddles are already constructed in native workspaces, so merely
sharing them does not remove the per-observation transforms.

## One experiment worth running

Reuse the complex lag-4 correlation already calculated at the selected native
coarse epoch to propose CFO. The current differential coarse path calculates

```
d_L(e) = sum_k y_e[k+L] conj(y_e[k])
                 conj(t[k+L] conj(t[k]))
```

with `L=4`, then keeps only `abs(d_L)` when it ranks timing cells. Under a
carrier offset `f`, the unknown complex amplitude cancels in the lag product
and

```
arg(d_L) ~= 2 pi f L / rate  (mod 2 pi).
```

The phase therefore proposes

```
f_m = rate * arg(d_4) / (8 pi) + m * rate / 4,
```

for every integer `m` that places `f_m` in the existing `[-400, 400] kHz`
search interval. There are at most two such aliases at 2.5 Msps and one at
5 Msps. This uses a sufficient statistic already paid for by coarse timing on
every blind receiver-visit. It does not depend on a prior positive, another
receiver, another channel, or a stale observation.

Freeze one candidate before opening scores:

1. Preserve the current differential fold, projected timing cells, native
   local refinement, selected epoch, support, and tie rules. Return the complex
   `d_4` from the selected local cell in addition to its existing magnitude.
2. Enumerate every in-range phase alias. Around each alias evaluate exactly
   three conditioned CFO cells at `alias - 100`, `alias`, and `alias + 100 Hz`,
   clamped and deduplicated at the existing carrier bounds. Use the existing
   conditioned score and existing best-frequency tie rule.
3. Continue through the unchanged five-cell epoch lattice, fractional fit, and
   full-support exact/control GLRT. Preserve the strict margin gate and existing
   candidate identity rules. A phase failure is an explicit candidate failure;
   it may not silently borrow the reference CFO.

This replaces the broad fine FFT with at most six conditioned cells at 2.5
Msps and three at 5 Msps. The experiment deliberately does not add a second
lag, tune an alias offset, reduce support, or alter thresholds after observing
development results. Tone, multipath, discontinuities at the rounded frame
seam, and low-SNR phase bias are the main scientific failure modes; the frozen
comparison measures them rather than assuming the phase model is exact.

## Cost ceiling and decisive gate

The measured server profile attributes 2.193 ms at 2.5 Msps and 6.316 ms at
5 Msps to the entire fine stage across 16 receiver-visits. Perfect removal of
that stage, while retaining the measured outer packing cost, caps whole-call
speedup at 1.098x and 1.133x. With packing already removed, the corresponding
native-dwell ceilings are 1.168x and 1.244x. Thus this experiment cannot by
itself establish 10x. It is still the one untried algebraic reuse that removes
a complete search loop on all visits, including the 220 development
reference-negative or unknown receiver-visits.

Run the common-profile packed reference and the new natural-stride candidate
on all 256 development receiver-visits and the 24 supported receiver-controls.
Use counterbalanced order, one warmup, five timed repetitions, and medians of
the full caller CPU and wall boundary. Report coarse, phase proposal,
conditioned-cell, fractional, and total costs separately.

Reject without retuning or holdout access if any of these occurs:

- fewer than 36/36 reference positives match within 8 kHz CFO and two
  microseconds circular timing;
- any new or lost positive among the eight pilot, eight noise, and eight tone
  receiver-controls;
- any change in fractional-complete or support validity for a matched reference
  positive;
- the replacement fine stage is not at least 2x cheaper at each rate; or
- full caller CPU does not improve by at least 5% at each rate.

Passing these development gates would justify one independently frozen
validation run, not a 10x or production claim. Holdout, ARM speed claims, RF,
and deployment changes remain outside this experiment.

## Receipt basis

- Development outcome receipt: `dev_dual_cfo_v4.json`, SHA-256
  `6f46c25db42c37f1eb1684369ec0ff7410a5d327e8c8c133a310ea09123522a9`.
- Blind stage-cost receipt: `scout/blind_cost_receipt.json`, SHA-256
  `935d89bcdf39f3b8414ffa81f280feeb7e0a826e7c555133ccc16ff37785fd78`.
- Existing cross-channel raw-prior audit:
  `review/cross_channel_dev_v4.json`. It finds only three of 36 positives with
  a prior cross-channel timing hypothesis within two microseconds and none also
  within 8 kHz without a CFO transform.

This review used receipt JSON only. It did not load development or holdout IQ.
