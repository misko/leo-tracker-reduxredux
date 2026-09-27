# Cached known-channel acceleration review

This review covers causal state, cost accounting, and the route to an ARM
qualification. It uses source metadata, development results, synthetic timing,
and older read-only evidence. It does not inspect held-out IQ or contact the
radio.

## The 10x budget

Let `B` be reference blind service per receiver-visit, `C = cB` a cold,
discovery, or fallback service, `H = hB` a successful cache-hit service, and
`f` the fraction of all receiver-visits which use `C`. The all-visits normalized
cost and the necessary hit-cost bound are

```
a = f*c + (1-f)*h
h <= (0.1 - f*c) / (1-f).
```

If `f*c >= 0.1`, 10x is impossible even with free hits. If `h >= 0.1`, any
nonzero baseline-cost cold fraction makes 10x impossible.

Every 64-visit block has four channels and two independent receivers. Even if
every channel is persistent, each receiver needs four cold acquisitions. That
is 8 cold calls among 128 receiver-visits, or `f = 6.25%`. For `C = B`, hits
must cost at most `0.04B`: at least 25x hit-only speed. This is an optimistic
bound before expiry, periodic discovery, failed confirmation, or quiet
channels.

The public source counters add expiry pressure. With the declared two-second
TTL, the then-current development blocks have two same-channel gaps over two
seconds at 2.5 MS/s and one at 5 MS/s. If all corresponding states exist, the
combined development minimum is 11 full blind calls per receiver pair per 128
visits, `f = 8.59375%`, and hits must be at least 65x. A 64-visit block with one
such expiry requires at least 42.14x hit-only speed. The 2.5 MS/s development
block with two expiries requires about 145x.

The same-library synthetic benchmark in `native/benchmark.json` reports only
10.44x hit-only CPU speedup at 2.5 MS/s and 11.97x at 5 MS/s. Even with only the
minimum cold fraction, those ratios cap optimistic all-visits speedup at about
6.57x and 7.10x. The benchmark supplies a contiguous selected window directly;
it omits normal grouped-RX selection and packing. The current full-aperture
point-confirmation design therefore cannot meet all-visits 10x even if every
cache prediction is correct.

Development replay `dev_point_v1.json` makes positive-only caching still less
suitable for the whole stream: it found 36 reference positives among 128 2.5
MS/s receiver-visits and none among 128 5 MS/s receiver-visits. Only two of 38
cache attempts succeeded and 254 of 256 visits ran blind fallback. These are
development outcomes, not absence truth. They show that quiet/reference-negative
visits dominate this replay and cannot be omitted from service accounting.

The first fitted-phase-rate replay, `dev_drift_v2.json`, retained all 36
reference positives and improved cache hits from 2 to 12, but still ran 244
blind calls among 256 receiver-visits. Its accepted-hit-only speedup was 4.93x
and its all-visits CPU speedup was 1.01x. This is useful evidence that phase
rate matters; it does not change the whole-stream conclusion.

Forced discovery every 32 accepted visits is not exercised by these blocks.
Each 64-visit block contains only 9--23 visits for any one channel, and session
is part of the state key. In a long steady state with `C=B`, forced discovery
every `k` hits requires

```
1/k + (1 - 1/k)*h <= 0.1.
```

At `h=.04`, `k>=16`; at the measured synthetic hit ratios, 2.5 MS/s needs about
`k>=215` and 5 MS/s needs `k>=57`. Thus the current 32-hit policy alone defeats
10x at 2.5 MS/s even after warm-up.

A 64-visit block is useful for an observed causal amortization result. It is
not 64 repeats per channel and cannot establish a rare fallback rate. With 60
post-cold opportunities per receiver and zero failures, the one-sided 95%
upper failure probability is still 4.87%. About 191 zero-failure hits are
needed to put that bound below 1.56%.

## What counts as end to end

The defensible 10x endpoint is post-capture processing service: selection,
packing, screening, confirmation, state, fallback, and queueing. If the fixed
120 ms recording dwell is included in latency, even zero processing cannot
produce 10x unless the reference processing takes at least 1.08 seconds per
visit. Neither the server nor prior ARM detector is near that value. Report
capture-to-decision latency, but label the acceleration claim as processing
service or throughput.

CPU demand must sum both receivers and every action, including a failed fast
attempt followed by blind fallback. Wall time may also report a fixed deployed
schedule. Parallel use of two Cortex-A9 cores can reduce latency but does not
reduce total CPU service. Queue qualification should replay original arrival
times and report utilization, queued decision age, and fallback bursts. A
skipped or unavailable visit is `unprocessed/unknown`; it is never a measured
negative.

`review/queue_dev_direct_v3.json` applies that accounting to the full-aperture
V3 development replay. It sums median receiver costs for each physical visit
and serializes visits from their capture-complete source counters, resetting at
the two session boundaries. All 128 physical visits and 256 receiver-visits
were processed; skipped/unknown count is zero. Candidate CPU service was 4.35
ms p50, 6.63 ms p95, 7.08 ms p99, and 7.18 ms maximum. The actual interarrival
median was 140.19 ms, so this server replay accumulated zero queue wait and
missed none of 126 next-arrival deadlines. This is server headroom, not ARM
real-time evidence and not a 10x result: candidate mean service was 4.47 ms
versus 4.51 ms for the reference.

The rate-matched accepted-hit accounting is stricter than the synthetic
benchmark. At 2.5 MS/s, 12 accepted full-aperture hits cost 2.351 ms against
18.599 ms for their paired references, normalized `h=0.1264`. Since `h>0.1`,
no nonnegative full-cost route fraction can yield 10x. There were no accepted
5 MS/s fast cases, so no real-data fast cost may be transferred to that rate.

## Causal-state review

The key `(session, receiver, channel, edge, rate)` and exact integer-first
source-counter modulo are appropriate. Native phase normalization originally
used the rounded template length rather than the exact `rate/750` period. That
shifted seam predictions by one-third sample at both supported rates. The
native implementation now uses the physical period; seam tests at huge
counters remain required.

Predicted point scoring fits fresh CFO innovation but does not fit timing. The
state must therefore distinguish:

- last accepted confirmation, for TTL and discovery count;
- last independently fitted timing anchor, for timing-rate learning;
- predicted scoring CFO, which must remain inside the native NCO bound; and
- physical tracking CFO, used for rate learning and reference association.

Overwriting the fitted timing anchor on every `predicted_verified` hit causes a
specific bias. Suppose the true phase rate is 15 samples/s. A cold fit occurs at
`t=0`, a point score at `t=.4` accepts the unchanged prediction while the true
phase is six samples away, and blind fallback at `t=.5` fits 7.5 samples. If the
point hit replaced the fitted anchor, the update estimates `7.5/.1 = 75`
samples/s rather than `7.5/.5 = 15`. Keep a separate fitted reference and learn
only across fresh fits. Point hits may refresh confirmation age and propagate
the existing model.

A fallback may preserve or update rates only when the strategy's own fitted
observation is compatible with the previous trajectory. The independent
reference comparator must never seed or repair state. An incompatible fallback
starts a new trajectory and clears derivative estimates.

Blind candidates can have an acquired/scoring CFO within the +/-400 kHz search
range and a physical tracking CFO just outside it after the GLRT residual. A
single `cfo_hz` field either rejects valid edge candidates or passes an invalid
NCO to the next call. Store both. Clamp or select the next scoring NCO within
the native range, compare physical tracking CFO for identity, and require the
expected residual from the scoring NCO to stay within the declared innovation
support.

The dev oracle has a more concrete case: acquired/scoring CFO is about 103.8
kHz while physical tracking CFO is about 5.2 kHz. Passing 5.2 kHz back as the
next scoring NCO loses the baseline result. State should preserve the
scoring-minus-tracking offset and advance both by the physical CFO-rate.
Known-state acceptance should compare returned physical tracking CFO with the
predicted physical value. The raw GLRT residual may legitimately be much larger
than 8 kHz because it includes the expected scoring offset; a native status bit
which applies 8 kHz directly to that residual is not the trajectory innovation
gate.

The tracker API currently relies on the caller to invoke `accepts` before
`update`. A positive but incompatible observation can mutate state if a caller
forgets that step. A later port should make accepted-update and
discovery-update separate checked operations. Policy values also need finite,
nonnegative validation and a frozen digest.

The V3 native port now separates scoring CFO from expected physical CFO and
the synthetic edge test accepts a physical result just beyond 400 kHz when its
scoring NCO remains at 390 kHz. It also preserves the large, expected offset in
the concrete 103.8/5.2 kHz oracle geometry while applying the 8 kHz gate to
physical innovation. Its expected scoring-to-physical residual is bounded by
the GLRT residual support rather than the scoring-NCO bound. This resolves the
dual-CFO contract mismatch for the tested geometries; it does not add a carrier
edge qualification on real data.

The configured discovery interval and the implementation should use one
explicit counting convention before a frozen run. The current tracker stores
zero after discovery and forces another discovery when
`accepted_since_discovery >= interval - 1`, so an interval of 32 permits 31
cached accepts after the discovery observation. If the policy phrase “after 32
accepted hits” excludes the discovery observation, the threshold is off by one.
The distinction is small for this short replay but changes the steady-state
cost bound and should not be decided after holdout outcomes.

## Native and replay accounting

The known-state port uses the newer decision-band scientific profile for both
candidate and blind reference. A valid fast result needs fractional scoring,
valid bounds, at least two support frames, strict margin greater than .025, and
no timing/CFO reacquisition status. Report its timing as
`predicted_verified`, never fitted timing.

The Python wrapper's earlier `np.ascontiguousarray` happened before the native
timer. A natural `raw[:, receiver, :]` view is strided, so C-only timing omitted
real packing cost. A bounded exploratory server check found the full wrapper
median increased from roughly .14 ms to .80 ms at 5 MS/s for a noncontiguous
view while the C timer remained near .14 ms. These concurrent measurements are
diagnostic, not qualification. Replay timing around the full Python call is the
right current boundary. A strided native API which ingests only samples touched
by the GLRT is the better implementation.

Reference-first timing warms the IQ and native tables before every candidate
action. Counterbalance order or disclose this candidate-favoring cache effect.
Summaries must include lost reference positives, additional candidate
positives, no-candidate observations, unsupported results, and unprocessed
visits. Pass counts alone are insufficient.

## Architecture with a possible 10x path

Positive caching alone cannot accelerate the quiet visits seen in development.
Use two measured stages on every visit:

1. Run the existing full-dwell, CFO-invariant lag/pilot rank screen. On
   development, choose and freeze a conservative score/contrast rejection
   threshold below every reference-positive example, with an explicit margin.
   A below-threshold result is a candidate detector-negative, not a physical
   absence claim and not a skipped visit.
2. For screen-positive visits, use a valid cached point confirmation when state
   exists; otherwise run blind acquisition. Any failed or incompatible cache
   confirmation runs same-visit blind fallback and charges both actions.

The rank API is currently documented as a proposal, so this is a new detector
stage requiring reference-positive retention and separate known-pilot, tone,
and noise controls. The 5 MS/s development block contains no positives and
cannot calibrate transfer sensitivity at that rate; held-out retention is the
first independent check and must remain explicit. If rank cost plus unavoidable
blind calls cannot fit the algebraic budget, stop before ARM work.

The bounded development scout has now ruled out both proposed screens. At
thresholds retaining all 36 development reference positives, native rank routed
222/256 receiver-visits and the independently normalized lag-3 RMS screen routed
231/256. Even free screens would cap speedup at 1.191x and 1.129x. Measured
packing plus the complete screen call reduced the modeled paths to 0.767x and
0.803x. Every known-pilot, tone, and noise control routed at both rates under
both thresholds, and development had no 5 MS/s reference positives with which
to qualify transfer. Neither screen should open fresh holdout; the immutable
development result is `scout/results.json` with SHA-256
`e21e363e28dba103c9336fad411b59c71700282647ef9089d9b18b9821795e18`.

A bank of timing/CFO hypotheses learned from other channels is a valid way to
order positive searches, provided each hypothesis scores fresh IQ and a miss
falls back to blind acquisition. It cannot solve the whole-stream budget in
this development mix. Only 36/256 reference outcomes are positive, so even
free, perfect handling of every one followed by baseline-cost processing for
the other 220 caps speedup at `256/220 = 1.164x`. The two-frame cached point
path measured 24.05x on its 12 accepted hits, or normalized `h=.0416`; one such
attempt leaves only about 6.1% baseline-fallback budget for 10x, and two
full-cost attempts leave about 1.7%. Quiet visits exhaust either budget unless
another detector measures them cheaply.

Cross-channel transfer should initially share timing hypotheses only. Relative
CFO depends on tuning and channel; it needs a frequency-aware offset model
learned from compatible accepted observations, with per-channel scoring NCOs
and physical-CFO innovation gates. Keep a small causal bank, try hypotheses in
prior confidence order, charge every attempt, and never interpret exhaustion
as absence. This may reduce positive latency or blind search ordering, but its
whole-stream value must be measured rather than inferred from hit count.

The raw causal-oracle audit in `review/cross_channel_dev_v4.json` gives little
evidence for direct reuse. Of 36 development reference positives, 34 had a
prior positive within two seconds and 28 had one from another channel. Only 16
had any prior lattice within two microseconds, only three had such a prior from
another channel, and none of those cross-channel priors was also within 8 kHz
without a CFO transform. This audit uses reference outcomes only as an
optimistic diagnostic and deliberately fits neither timing drift nor channel
CFO offsets. A later affine model could improve those counts, but it must do so
causally on development before it justifies a detector experiment.

The remaining route to a large whole-stream gain is a blind detector rewrite
which produces an outcome on every visit. Current outer median cost is about
1.55 ms at 2.5 MS/s and 3.30 ms at 5 MS/s, so 10x budgets are .155 and .330 ms.
Receiver packing alone is approximately .58 and 1.25 ms, already beyond those
budgets; strided or grouped dual-receiver ingest is necessary. Native dwell is
still about .97 and 2.05 ms after packing, so it also needs a substantial
algorithmic reduction. The strongest bounded direction is to fuse streaming
rank/acquisition sufficient statistics, batch CFO-by-epoch evaluation with
FFT/SIMD reuse, and prune coarse-to-fine tiles only with an admissible bound on
the exact/control objective. Cached hypotheses can set search order inside
that detector. A partial-frame blind GLRT is another legitimate detector, but
it has a different statistic and requires development thresholds, controls,
and independent retention qualification; a partial cached point score does not
qualify the blind search.

For persistent positives, further hit optimization should fuse strided CI16
ingest with the exact/control correlations and avoid converting the unused
parts of a 20 ms interval to complex128. A two-frame or sparse-frame screen can
be explored only as a separately qualified detector. It must measure fresh IQ
on every visit and retain all reference positives; periodic full confirmation
does not turn intervening skipped visits into detections.

The V2 synthetic benchmark demonstrates the performance direction. Direct
strided, selective ingest raises full-aperture wrapper-wall hit speedup to 8.89x
at 2.5 MS/s and 10.06x at 5 MS/s. Four-frame scores reach 28.2x and 34.8x; two
frames reach 39.2x and 54.0x. Full aperture still cannot meet the cold-start
budget. Partial support can meet the optimistic no-expiry 25x hit bound, but
the four-frame variant misses the 42.14x one-expiry bound at both rates and the
two-frame variant narrowly misses it at 2.5 MS/s. These are synthetic ratios,
and partial scores have a different, unqualified statistic. A seven-case
same-visit dev oracle check showed no additional trusted-pass losses relative
to full aperture, but it is noncausal and far too small for qualification.

## Adversarial qualification

- **Wrong positive cache:** seed state from a strong but different pilot and
  present the intended pilot on the next visit. The cache result must fail
  margin or innovation, invoke same-visit blind acquisition, and update only
  from the accepted strategy result.
- **Close interferer:** synthesize two pilots around 7,999/8,001 Hz CFO and
  1.9/2.1 microseconds circular timing separation. Verify strict association,
  exact/control behavior, and no trajectory hijack.
- **Drop and retune:** include an unprocessed range, a source-counter gap, and
  changes of session/channel/edge/rate. Outage rows stay unknown, age advances,
  stale state expires, and no state crosses a key or retune.
- **Fractional-period seam:** test both sides of the 2.5 and 5 MS/s `rate/750`
  seam, negative fractional offsets, counters above `2**55`, and 64 causal
  advances. Native and Python source coordinates must agree without float
  accumulation.
- **Point-hit then fitted fallback:** use the 15-sample/s example above and
  prove the fit-to-fit estimate remains 15 samples/s.
- **Carrier edge:** acquire within +/-400 kHz with physical tracking CFO just
  outside it. The next scoring CFO stays supported while physical identity and
  rate use tracking CFO.
- **Fallback burst:** consecutive cache failures charge fast plus blind on each
  visit. Failed results never refresh TTL, discovery count, or fitted anchors.
- **Dual receiver:** one receiver hits while the other falls back; total CPU is
  their sum and state remains independent.
- **Controls:** noise and tones do not become positives in fast, sparse, or
  rank-negative stages. A known pilot remains positive at both native rates and
  at support boundaries.

## ARM route

An existing saved-IQ ARM qualification route is available in
`reports/figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/arm-cadences/qualify_tracking_cadences_arm.py`.
It targets serial-bound `radio_pluto_5d4d` at the recorded endpoint, uses the
`LocalCaptureAuthority` lease and serial radio lock, strict known-host SSH,
before/after TX-safe idle attestation, hash-checked payloads, a UUID temporary
directory, bounded timeouts, result retrieval, and cleanup. The local cross
compiler path and Cortex-A9/NEON flags also have prior build recipes. Current
reachability and lease availability were deliberately not probed.

The appropriate final ARM action is saved-IQ compute replay only: build and
hash-pin one software winner, claim the lease, attest idle, upload binary and a
small frozen saved-IQ set, run bounded serialized repetitions, retrieve raw
journals, remove temporary files, and prove before/after state equality. It
needs no new RF collection and no persistent installation.

Older ARM evidence is useful only for feasibility. A different detector
profile measured mean blind CPU around 36.35 ms at 2.5 MS/s and 62.98 ms at 5
MS/s, with final confirmation alone around 4.73 and 7.25 ms. A separate saved-IQ
pilot moments/solve benchmark measured about 2.125 ms per observation but
excluded capture, logging, and the full GLRT detector and was explicitly not
native-tracking qualification. Neither result can substitute for a same-build,
whole-pipeline ARM replay.
