# Lag-3 proposal feasibility result

## Decision

Reject this implementation as the proposed route to the server budget. The
complete natural-stride proposal call took a median **0.461075 ms at 2.5
Msps** and **0.9943485 ms at 5 Msps**, versus the frozen **0.080 ms** maximum
at each rate. Those are 5.76x and 12.43x over the primitive budget. Per the
preregistered stop rule, no blind-detector replay, GLRT integration, tuning,
holdout access, RF work, or ARM execution followed.

This result rejects the measured implementation and its dense full-visit
workload. It does not establish a lower bound for every possible lag-3
implementation.

## Frozen primitive

The kernel reads a full 120 ms dual-receiver CI16 allocation by sample-aligned
base plus explicit receiver lane. For each of six 20 ms windows it computes the
exact dense int64 `b*conj(a)` fold at lag 3 over 15 rounded 750 Hz frame starts,
projects to 512 timing cells, and runs a single point-projection correlation.
It streams the best three circular local maxima with a frozen score/window/bin
tie rule.

For each selected peak it refines integer timing over the frozen native offset
radius `ceil(n/(2*512))`, then recomputes a centered direct native lag-3
correlation. CFO is `arg(R3)*Fs/(2*pi*3)`. The implementation exposes raw
complex `R3`, normalized magnitude, and separate phase support. Phase support
requires normalized magnitude at least 0.05; overall proposal support also
requires the returned principal CFO to lie within +/-400 kHz. A weak phase is
unknown CFO evidence, not an absence decision.

Lag 3 is alias-free over +/-400 kHz, but it is not generally unbiased. Unknown
data, a frequency-selective channel, mixtures, fractional timing, and rounded
physical frame boundaries can rotate the direct correlation. The synthetic
component checks therefore establish bounds and sign convention only.

## Measurement

The run used all 128 frozen new-development visits, both receivers, and both
rates: 128 receiver cases and 384 timed calls per rate. Each receiver case had
one warmup and three measured calls. Receiver order alternated by case and
repetition. The outer clock was Python `time.thread_time_ns` around the complete
`Lag3Proposal.run` call, including contract validation, ctypes ingress, the
native full-visit primitive, and result conversion. Workspace/template setup,
file IO, source/IQ hashing, and the post-call mutation hash were outside the
timed interval.

| Rate | caller CPU median | caller CPU p95 | wall median | native CPU median | gate |
|---|---:|---:|---:|---:|---:|
| 2.5 Msps | 0.461075 ms | 0.486026 ms | 0.460669 ms | 0.449968 ms | fail |
| 5 Msps | 0.994349 ms | 1.345927 ms | 0.993915 ms | 0.973634 ms | fail |

The native median split was 0.310012 ms fold plus 0.137182 ms correlation at
2.5 Msps, and 0.652368 ms fold plus 0.313472 ms correlation at 5 Msps. Dense
folding alone exceeds the complete 0.080 ms target at both rates.

## Independent constructed-control diagnostic

After the cost result was frozen, the independent `lag3_validation` runner
scored the same binary on 40 receiver controls. This was a proposal-coordinate
diagnostic only, with the unchanged 2 us circular-timing and 8 kHz CFO
association. It carried no performance timing and did not run or qualify a
detector.

The primitive jointly matched timing and CFO for only **9/24** strong
single-pilot receiver controls: 3/12 at 2.5 Msps and 6/12 at 5 Msps. It matched
0/4 pilot-plus-tone controls. In two-pilot ambiguity cases it matched either
declared trajectory for 2/4 receivers, both at 2.5 Msps; all three 5 Msps
proposals were supported in both receiver cases but matched neither injected
trajectory. Noise and tone produced zero supported proposals across eight
receiver controls. These counts are proposal behavior, not calibrated recall
or false-positive rates.

The dominant failure was wrong projected timing, often by hundreds of
microseconds, beyond the frozen local native refinement radius. For example,
the 2.5 Msps zero-CFO pilot RX0 proposals were 638.5 us from truth with maximum
phase support 0.037, while the 5 Msps +399 kHz integer pilot RX0 proposals were
at least 552.3 us from truth with maximum phase support 0.022. This shows that
the 512-cell point-projection rank is not a reliable timing proposal for these
constructed signals. The result is a second independent rejection reason; no
peak-count, projection, support-threshold, or refinement-radius tuning followed.

The runner asserted exact candidate tuple determinism over all measured calls,
verified every input hash before and after its calls, and validated source,
dataset, and binary receipts. Component tests cover both rates and receiver
lanes, direct phase sign at 0/positive/negative/near-boundary CFO, fractional
timing, circular seams, zero/tone support behavior, CI16 extrema, malformed
layouts, and caller-IQ immutability. The test helper's continuously repeated
template is a convention/lattice stress case; the separately frozen
`lag3_controls` corpus supplies rounded-frame discrete placements and ambiguity
cases for independent proposal diagnostics.

## Receipts

- `design.json`: `2db00353d1738f9d7b34eca09d8399e1e72253d593de8c08d2ad1d9eb5ea8f81`
- `lag3_proposal.c`: `b2b214d99369b311e6bcd4113c990bade612c8c805393ddc9c78207493b440ab`
- `lag3_proposal.py`: `e5f301be7752bf065ae81c87327388dd62cdb55ba0f32737ca37610c4b9c8057`
- `liblag3_proposal.so`: `af7b708624b130479149eb721ad66067583f64a3da5833d7688eb05623f958bb`
- build receipt: `adcbf768dc1b01c85e896e3e0870ceeb38c30833650356b9c8d516bbe2cdca14`
- `cost_results.json`: `a1210132c49601ca4b9687d01a1b486ff12696bcd279bf534ab1701314553a5f`
- independent control result: `8c7b633718883ff33315411629936f226fd22ece62c103d3c7a9403db72bd336`
- new-development manifest: `b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845`
- constructed-control manifest: `5bc58aab84ce75d3704d08a294333010745caec382da5f059b04c9e5a5473188`
- scientific review: `1b7ff1ad83fb76b39b2a42e5b736b05449506ce65bc28919d6d0dcb8fbba5fa6`
