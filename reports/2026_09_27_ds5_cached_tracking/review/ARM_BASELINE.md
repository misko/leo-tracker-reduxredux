# ARM baseline and the valid 10x denominator

## Finding

There is no existing ARM measurement of the frozen cached-tracking common
baseline.  The current repository's Standard Python analysis, the deployed
host decision lane, the last qualified on-radio ARM detector, the radio `.20`
acquisition/tracker, and the new server replay are different workloads.  Their
timing numbers cannot be combined into a 10x claim.

The server common baseline is numerically much faster than the historical ARM
paths: its packed blind reference averages 1.508 ms per receiver-visit at
2.5 MS/s and 3.036 ms at 5 MS/s.  Historical production ARM
confirmation-bearing jobs averaged 70.21 and 141.57 ms respectively.  The
rough ratios are 46.6x at both rates, but they are cross-machine diagnostics,
not speedups: the production build has a different frozen algorithm, uses
ARM FFTW, processes one selected receiver, and has different admission and
timing boundaries.  The common baseline has therefore not been shown faster
than the user's current pipeline on the target ARM.

The next valid *common-profile* measurement is a saved-IQ, paired Cortex-A9
replay of the frozen common baseline and candidate.  It must time all visits,
including quiet visits, failed predictions, expiration, discovery, and blind
fallback.  The 7.38x server cache-hit-only result is not an end-to-end result;
the full development replay is 1.477x.  This result must remain labeled as a
common-profile research result.  It cannot be renamed after execution as a 10x
improvement of the Standard Python analysis.

## The three scanner contracts

The intended production operation is ambiguous unless one of these contracts
is named explicitly:

| Contract | Input and detector work | Decision semantics |
| --- | --- | --- |
| This repository's Standard scanner | A 120 ms dwell, normally both RX; 11 overlapping 20 ms probes at 10 ms stride; acquisition and GLRT scoring for up to the configured candidate limit on every probe | Positive only after two same-RX, non-overlapping probes pass the margin gate and their tracking CFOs differ by at most 8 kHz |
| Deployed September 13 adaptive lane | One physical RX at native 10 MS/s; factor-four 2.5-MS/s host stream; six screens and at most one blind confirmation | Per-visit adaptive feedback; on-radio GLRT disabled |
| Cached-tracking common research profile | Each RX evaluated separately at native 2.5 or 5 MS/s; six non-overlapping 20 ms windows ranked and at most one confirmation, or a known-state attempt plus fallback | Reference-relative one-window detection; no two-probe CFO-pair requirement |

The Standard implementation is
`src/leo/scanner/detector.py::analyze_glrt64_dwell`.  It records responses for
every acquired candidate, not just the winning window.  `ScannerConfiguration`
defaults to eight retained acquisition candidates; the current CLI/composition
front doors override that to ten.  A comparison against recorded DS5 must use
the exact persisted source configuration rather than choosing eight or ten for
timing.  The extracted `cases.json` does not carry that full detector
configuration.

DS5 supplies 120 ms dual-RX visits at 2.5, 5, 7.5, and 10 MS/s.  That geometry
does not by itself select one of the three decision contracts.  In particular,
the common native library currently accepts only 2.5 and 5 MS/s.  Results on
those strata do not establish a replacement for the Standard analyzer at all
four DS5 rates.

## What is currently deployed

The latest retained production-deployment evidence is the September 13 host
adaptive scanner, not an on-radio ARM GLRT service:

| Property | Deployed production path |
| --- | --- |
| Release | `52313e7fc0b9f9f978fb0f613d25c1d152fce238` |
| Radio | `.17`, serial `104000bac4950008230026001b440a003a` |
| RF input | One physical receiver chosen once per 300 s recording; native 10 MS/s |
| Decision stream | Manifest-bound factor-four 2.5 MS/s stream on the host |
| Decision work | Six 20 ms temporal screens and at most one blind confirmation per 120 ms visit |
| Cadence | 300 s acquisition every 600 s; 2,381 visits in the first scheduled production capture |
| Observed decision bound | Maximum host result age 165.557 ms; maximum applied feedback age 270.323 ms |
| On-radio GLRT | Disabled |

The 165.557 ms value is a result-age bound, not detector CPU time.  The
production report does not publish a matched per-visit CPU denominator for this
release.  The 412.064 s background-analysis cycle includes refinement,
tracking, and publication over the whole recording; it is not the online
decision service time.

The earlier September 10 qualified ARM scanner is useful hardware evidence but
is not the current deployment.  It processed RX1 only, at native 2.5 or
5 MS/s, with six-window screening and at most one confirmation.  Its service
goal was 100 ms CPU, with a separate 500 ms worker watchdog.  The source
schedule supplied 120 ms visits, eight-visit read-ahead, and a 64-visit storage
queue.

| Qualified ARM scanner cohort | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Confirmation-bearing CPU, mean / p99 | 70.21 / 84.49 ms | 141.57 / 169.34 ms |
| Same jobs wall, p99 / maximum | 89.22 / 95.41 ms | 189.76 / 203.39 ms |
| Complete temporal screens | 2,364 / 2,364 | 588 / 2,357 |

The 5 MS/s overload produced 1,769 visits with no search mask.  Those visits
were reported as unavailable and remain unknown; their zero compute cannot be
counted as a speedup.  A later ordinary 5 MS/s capture screened 660 of 2,363
visits, with 136.11 ms mean and 172.62 ms p99 CPU over the screened cohort.

That production ARM worker used the deployed bundle manifest
`19c3650480a8386b12384b0f9a0c5d49e237b04ad98f474d3f820ddd7c`, worker binary
`b83aa9da09914a8019544af29bc41e2fdf3023e951bd961973be90049bf2917f`,
and double-precision ARM FFTW (`LEO_PRESENCE_FFTW=1`).  Its build predates the
energy-support flags in the common research profile, and its `presence.c` hash
is different.  It is therefore not the scientific denominator for the cached
tracking experiment.

## Other ARM evidence and its boundary

The September 12 decimated-dwell replay is the closest existing execution of
the newer detector family on Cortex-A9.  It uses the same main
`presence.c`, `fft.c`, `window_rank.c`, and `dwell.c` hashes and the later
hybrid-rank, diversity, amplitude, rotation, bounded-magnitude, and energy
support flags.  Presence transforms use production double-precision ARM FFTW;
an isolated static NEON FFTW-float library is used only by the experimental
10-to-2.5-MS/s FFT decimator.

On 16 development dwells, that FFT-decimated replay measured 306.012 ms mean
filter CPU, 54.383 ms mean detector-worker CPU, and 364.817 ms mean pipeline
wall time.  It was a saved-data development replay, excluded extraction,
transport, feedback, and queue pacing, and failed the declared real-time gate.
It is evidence that this detector family executes on the target architecture,
not an ARM timing result for the frozen common baseline.  The isolated float
FFTW dependency was explicitly research-only; production libraries were not
changed.

The radio `.20` acquisition/tracker is a third detector family.  It exports
2.5-MS/s IQ from native 30/60 MS/s, scans 14,000 samples with two ARM threads,
orders eight basins, resolves four approximately 3,300-sample pilots across 17
timing hypotheses, and then runs retained-IQ catch-up and native FPGA feedback.
The default bounded profile has a 12 s worker deadline, six attempts, a 3 s
resolver budget, a 3 s native-controller budget, and a 25 s process alarm.
Qualified live NEON timings were 472.28--533.12 ms for coarse scan,
538.57--599.43 ms through ordering, and 601.39--613.22 ms for resolution and
initial catch-up.  Fresh acquired feedback, autonomous scanning, and sustained
loss/reacquisition were not qualified.  These numbers cannot be compared with
one 120 ms `native_presence` receiver-visit.

## Frozen server research baseline

The current common profile is
`reports/2026_09_27_ds5_cached_tracking/native/profile.json`, SHA-256
`3c96186ad0e22b6e948f90ad9fd33a54508c94ae6e376b367064d36b804fc1a1`.
It accepts native 2.5/5-MS/s input, evaluates six 20 ms windows per 120 ms
receiver-visit, and uses the later research flags listed in that file.  The
server binary uses the builtin FFT implementation; it is not the production
ARM FFTW build.

The final development replay is
`dev_strided_v6_final.json`, SHA-256
`e2528d2a77d4818945c273db77272eb5e8d69f258e2ae664ecda1f3870a82d63`.
Its stated scope is “causal saved-IQ server replay; not ARM qualification.”

| Frozen server development result | 2.5 MS/s | 5 MS/s | Combined |
| --- | ---: | ---: | ---: |
| Receiver-visits | 128 | 128 | 256 |
| Packed blind reference CPU | 192.989 ms | 388.570 ms | 581.559 ms |
| Reference mean per receiver-visit | 1.508 ms | 3.036 ms | 2.272 ms |
| Full candidate CPU | 123.140 ms | 270.724 ms | 393.863 ms |
| Full candidate speedup | 1.567x | 1.435x | 1.477x |

The combined candidate made 240 blind calls, 51 cache attempts, and 16 accepted
cache hits.  It retained all 36 reference positives and reported three
additional relative positives.  Accepted cache hits alone were 7.381x faster,
but they covered only 16 of 256 receiver-visits.  A deployment comparison must
use the full 256-visit numerator and denominator.

## Three distinct 10x claims

### Common research baseline

Use this claim for the present optimization work:

`10x common-profile ARM speedup = sum(reference CPU service over every receiver-visit) / sum(candidate CPU service over those same receiver-visits)`

Freeze before execution:

1. The profile, source, templates, saved-IQ case hashes, compiler, Cortex-A9
   flags, FFT backend, thread count, affinity, and clock policy.
2. Identical baseline and candidate input support: same 120 ms, same receiver,
   same rate, and the same six-window reference opportunity.
3. Candidate accounting for selection/packing, cache lookup/update, fast
   attempts, failed predictions, periodic discovery, expiry, every blind
   fallback, and result construction.
4. All visits in source order, including quiet and control visits.  Skipped or
   unsupported work is unknown and remains in coverage accounting.
5. Separate 2.5- and 5-MS/s ratios.  A combined ratio requires a workload mix
   frozen before timing; it must not be reweighted toward the faster rate.
6. Matched reference-positive retention, CFO/timing association, controls,
   determinism, and source mapping.  Timing alone cannot qualify the candidate.

Initialization may be reported separately only if both systems are long-lived
and initialize once under the deployment contract.  Per-visit buffer
conversion, copies, queue operations, and fallback initialization belong in
service time.  Report wall time and queue completion in addition to CPU time.

An ARM build using FFTW can be a new, predeclared implementation profile if
both reference and candidate use the same backend and reproduce the frozen
server decisions within the existing tolerances.  Do not compare a new ARM
FFTW candidate against the server builtin-FFT denominator.  Likewise, a custom
FP32 backend needs its own matched reference build and numerical qualification.

### Current repository Standard analysis

If “current pipeline” means this repository's Standard GLRT64 analysis, its
denominator is the full `analyze_glrt64_dwell` call with the persisted
configuration for each visit.  Count all 11 probe positions, both physical
receivers, every retained acquisition candidate and GLRT score, construction of
all probe responses, and the same non-overlap/CFO-pair decision.  Include input
conversion and any native/Python boundary cost that the candidate still needs.

An accelerated result qualifies only if it preserves the complete candidate
and probe response contract and the same first-detection rule, or if a changed
output contract is explicitly evaluated as a separate scientific policy.  A
six-window rank plus one confirmation does less work and returns different
evidence.  Its time cannot be divided into the Standard analyzer's time and
reported as a 10x implementation speedup.

For an ARM claim, run an exact-semantics ARM port of this Standard denominator
and candidate on the same Cortex-A9 and saved visits.  If the practical goal is
instead to replace server analysis with a lighter online decision, compare
decision quality, coverage, and downstream compatibility separately; call the
timing result an architecture/policy comparison rather than an implementation
speedup.

### Deployed-pipeline replacement

A separate claim may compare against the current production release only after
the candidate implements its production input/output contract.  Freeze a
representative saved production schedule and count, for both methods:

- native-10-MS/s to decision-2.5-MS/s extraction and decimation;
- all six screens and the bounded confirmation;
- policy/cache state, all blind acquisition and reacquisition, and failures;
- queueing, copying, serialization, and publication through the same decision
  endpoint;
- every 120 ms visit, including below-threshold and quiet visits; and
- the deployed single physical receiver, or an explicitly normalized
  receiver-RF-second workload if evaluating dual-RX DS5.

For compute speed, start when the required IQ support is available and stop
when the decision is publishable.  Report capture-to-decision age separately.
The unchanged detector needs 120 ms of observation, so a 10x compute reduction
does not imply a 10x reduction in RF observation latency.  Full background
analysis, plotting, and tracking may be a third end-to-end metric, but then
both baseline and candidate must run the same complete 300 s product graph.

For the `.20` tracker, the only defensible 10x denominator is its own complete
acquisition-to-handoff path: coarse scan, basin ordering, resolution, catch-up,
native-controller work, unsuccessful attempts, and reacquisition over a fixed
source interval.  The cached-tracking server replay does not implement that
contract and cannot currently support this claim.

## Bounded ARM route

No hardware was contacted for this review.  The next route should use saved IQ
only and the existing serial-bound qualification pattern:

1. Name the target contract before execution: frozen common profile, exact
   Standard analyzer, or deployed adaptive lane.  Do not use one contract's
   timing as another contract's denominator.
2. Cross-build matched reference and candidate binaries for Cortex-A9/NEON.
   For the common-profile experiment, preserve its frozen scientific flags.
   Choose builtin FFT or ARM FFTW before seeing timing and use it for both
   binaries.
3. Verify binary, source, template, config, and saved-IQ hashes before and after
   execution.  Refuse a changed input rather than inheriting a receipt.
4. Use the existing ARM operator safeguards: serial lock, strict known host,
   idle attestation, unique temporary directory, finite process timeout,
   artifact retrieval, cleanup, and final idle attestation.  Open no RX buffer
   and submit no native job.
5. Run a small fixed development subset first, counterbalancing method order
   with three warm repetitions.  If decisions and controls match, run the
   predeclared validation subset once.  Do not open holdout to select an
   implementation.
6. Record process CPU and monotonic wall time for total service, plus per-rate
   distributions.  A later paced replay may evaluate queue stability against
   the actual source-counter arrival gaps.

The existing saved-IQ ARM recipes in
`tools/prepare_decimated_dwell_replay.py` and the serial/idle pattern in the
radio-tracking cadence qualifier provide the implementation route.  Any target
execution still requires coordination because it stages and runs code on the
radio.  No new RF collection is needed.

## Evidence identities

| Evidence | SHA-256 |
| --- | --- |
| Historical ARM coarse/catch-up evidence | `ad38e25f6f1293321de91f6b6671c3b420a3a7b5081ef329eca48bada6512050` |
| ARM original-epoch/NEON evidence | `6455493bae4302748e89aa3ea95f16e527a24849680e2bf8632846016f0d764a` |
| ARM cadence review | `407610b35c97dd8f4d49155241bab61deb6b6b717e77d46e0008c84fadec8b3f` |
| Decimated ARM research report | `d1966f86a0099a2b59c2eba08bb933f941715346831e244db18aea8765816358` |
| Decimated ARM summary | `92305ba53706398a30f0a19ddfebbbc9f68f258a57b1c06ac85b7af8ce5fba75` |
| Decimated ARM FFT build | `490dd4b424ce221763651fabce39726efbe8d3945f8099e5daed445c40c0f8f7` |
| Research FFTW-float provenance | `8d6bce83a5787538d0368a182a0c2fff93d47bfe34475b821bb90428e82135b1` |
