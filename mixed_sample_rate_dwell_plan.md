# Mixed 2.5/5/10 MS/s production dwell plan

## Outcome

Add a single auditable production scheduler and capture/analysis path for paired radios whose
sample rates may differ. Both radios observe the same randomly selected Starlink channel and
edge in every mixed-rate dwell. IQ remains native-rate throughout; there is no resampling.

The requested production allocation is interpreted additively:

| Dwell class | Share of scheduled recording dwells | Count per 16-dwell cycle |
|---|---:|---:|
| Mixed 2.5/5 MS/s | 37.5% | 6 |
| Mixed 2.5/10 MS/s | 12.5% | 2 |
| Existing ordinary profile pool | 50% | 8 |

The 37.5% 2.5/5 share comprises the requested 25% feature plus the additional 12.5% share in
feature two. Manual captures, qualification captures, scanner sweeps, retries, and coalesced or
cancelled intents are excluded from the denominator. If those percentages were intended as two
alternative configurations rather than one combined allocation, this policy must not be enabled
until the operator selects the desired configuration.

## Non-negotiable invariants

- Use only radios `192.168.1.20` and `192.168.1.21`; never discover or access a local radio.
- Use the pinned `/home/mouse9911/gits/pluto-plus-utils` interface for hardware qualification.
  Any required change to that project is reported before modification and published as an issue.
- Do not reboot the host or either radio.
- Both radios use the exact same Starlink channel and upper/lower edge for a mixed dwell.
- High-rate duty is balanced by radio over every 16-dwell cycle: three 5M assignments per radio
  and one 10M assignment per radio.
- Selection is deterministic from the durable cadence identity. A restart or retry cannot reroll
  dwell class, channel, edge, rate assignment, or radio role.
- Capture is counter-authoritative and device-axis zero-filled. Equal rate, duration, receiver
  geometry, and CI16 format imply equal logical/decompressed IQ length even when samples are
  missing. The validity inventory remains authoritative; zero fill is never treated as observed RF.
- Analysis consumes each stream at its captured native rate. No resampler, decimator, or packed-
  axis shortcut is allowed.
- Published V1-V3 contracts and the frozen Standard-v2 pipeline remain byte-compatible.
- Acquisition stays paused outside explicit bounded canaries and is paused at handoff.

## 1. Durable scheduling policy

Introduce an additive mixed-rate schedule contract with an exact 16-slot cycle. Each cycle uses a
digest-derived permutation containing six `mixed_2p5_5`, two `mixed_2p5_10`, and eight
`ordinary_pool` slots. Channel, edge, and which radio receives the higher rate are also derived by
domain-separated unbiased hashes of the immutable operation key.

Persist the fully resolved intent before lease execution:

- policy revision and cycle/slot;
- dwell class;
- selected channel and edge;
- ordered radio IDs and per-radio sample rate/bandwidth/profile revision;
- exact sample counts for the common duration;
- candidate ordinary-profile pool where applicable.

The executor reads only the persisted intent. Reclaim, retry, pause/resume, or supervisor restart
must not change it. Property tests cover many cycles, exact counts, radio balance, unbiased channel
and edge reachability, canonical serialization, and operation-key stability.

## 2. Additive mixed-rate capture authority

One legacy capture profile cannot truthfully describe two radio geometries. Add new contract majors:

- a mixed-rate profile/revision describing the allowed rate pair, common duration, receivers,
  buffer/storage policy, and fail-session semantics;
- a compiled capture plan binding every radio to its exact requested settings and sample count;
- a recording manifest binding the per-radio plans to existing device-axis stream receipts.

The coordinator keeps one readiness gate and common release target, but each radio drains until its
own device-axis endpoint. Admission sums the exact per-radio logical bytes and refill metadata.
Writer queues, counters, gap maps, literal zero-fill chunks, timing, and quarantine/poison behavior
remain per stream. Publication is fail-session and atomic.

The manifest validator closes, for each stream:

`requested settings -> applied settings -> rate-specific logical count -> physical chunks ->`
`timeline -> gap map -> validity inventory -> logical/observed IQ digests`.

It additionally proves the two RF centers encode the same selected channel and edge.

## 3. Native Standard analysis for unequal rates

Add a new Standard-native pipeline definition rather than weakening the existing common-rate
definition. It retains the same 12-job topology and scientific kernels:

- each receiver-path job uses that stream's exact rate-resolved production configuration;
- probe, FFT, frame, GLRT, QAM, CFO, Doppler, trajectory, and Kalman work is scheduled on each
  stream's own device-time axis and cannot cross a validity boundary;
- radio reducers combine only paths from the same physical stream/rate using sufficient statistics;
- paired reducers intersect validity on UTC time, not sample index or segment ordinal;
- cross-radio results are expressed in SI units and UTC so unequal sample indexes cannot alias;
- all 59 expected PNG products are rendered from sealed products, not raw IQ rereads.

The source bindings and promotion authority explicitly bind the ordered per-stream rates and the
mixed-rate pipeline definition. Existing same-rate 2.5/3/5 definitions remain readable and
unchanged.

Ten MS/s is admitted only after the direct native-rate oracle suite establishes pilot epoch,
CFO/rate, phase, QAM/EVM, Doppler, trajectory, GLRT geometry, gap exclusion, and deterministic PNG
publication at reviewed tolerances. Fifteen MS/s remains a separately named, disabled experimental
authority after its measured transport failure; it is not aliased to the 10M production class.

## 4. Performance and hardware gates

For dual-RX CI16, the nominal input rates are:

| Pair | Radio input | Aggregate input | Logical bytes per 60 s |
|---|---:|---:|---:|
| 2.5M + 5M | 20 + 40 MB/s | 60 MB/s | 3.6 GB |
| 2.5M + 10M | 20 + 80 MB/s | 100 MB/s | 6.0 GB |
| 2.5M + 15M (disabled) | 20 + 120 MB/s | 140 MB/s | 8.4 GB |

The last sealed incompressible-writer result was about 143.7 MB/s, so 2.5/15 currently has only
about 1.03x nominal headroom and is not production-qualified by configuration alone. The server's
2.5GbE upgrade may help aggregate ingress but does not prove the individual Pluto link.

### Measured remote-IP result (2026-08-27)

Pinned Pluto+ Utils `cb1d091cd5c5831d0a99347bf74fb4e517800c92` tested paired RX on only
`192.168.1.20` and `192.168.1.21`, with 262,144 samples/channel, 24 timed frames, two warmups,
and eight kernel buffers. Original settings were restored on both radios.

| Radio | 2.5M delivery | 5M delivery | 15M delivery | 15M achieved/offered |
|---|---:|---:|---:|---:|
| `.20` / serial `...5d4d` | 100.19% | 100.22% | 40.55% | 48.65 / 120 MB/s |
| `.21` / serial `...19f2` | 99.60% | 100.23% | 40.25% | 48.29 / 120 MB/s |

This is a hard 15M qualification failure. The 2.5/15 weight must remain zero and no 2.5/15 RF
canary or production deployment is permitted on the current per-radio IP data plane. Server-side
2.5GbE does not change that conclusion. Enabling the requested 12.5% 15M share requires a reviewed
radio transport/firmware change followed by this exact ladder and the full continuity campaign.

The maximum-buffer ladder was repeated at 10 MS/s after the host's 2.5GbE upgrade. Each radio used
4,194,304 samples/channel, four kernel buffers, two warmups, and six measured dual-RX frames through
the pinned utility. `.20` delivered 49.627 MB/s (62.03% of the required 80 MB/s) and `.21` delivered
56.949 MB/s (71.19%). Both settings restorations passed, but neither radio met the utility's 90%
keep-pace floor. Evidence is retained at
`/home/mouse9911/tmp_bkup/leo-native10-ppu-pt05HG/radio-{20,21}-10m.json` with SHA-256
`b1de5501acaf93862a98faf9d3672b798fffb12b77594cdde4e801004f11198c` and
`1f623350039b3de47730bfe9379259e533435b5509b5c709ac7554d4382b6c3b`. This is a hard 10M dual-RX transport failure: the
2.5/10 scheduler weight remains zero, and no 10M production capture is allowed on this IP path.
Software support remains dark so it can be requalified after a transport/firmware change; the
failure must not be hidden by dropping a receiver, decimating, or resampling.

Maximum safe refills also require a duration-aware metadata I/O timeout. A fixed five-second
timeout, originally sized for 262,144-sample refills, deterministically timed out the first
4,194,304-sample metadata refill on both radios even though the ordinary transport ladder kept
pace. Pluto+ Utils issue #42 and revision `cb1d091cd5c5831d0a99347bf74fb4e517800c92`
resolve the timeout as `clamp(8 * ceil(refill_samples / sample_rate), 5s, 30s)` before metadata
priming. The timeout remains finite and fail-closed; qualification must bind that exact utility
revision and prove the maximum-buffer metadata path, not only ordinary libiio throughput.

That exact metadata canary exposed a separate READBUFM transfer limitation. At 2.5 MS/s the
4,194,304-sample refill spans about 1.678 seconds, but each metadata request took about 4.95 seconds
and returned source sequence `+3`, proving two skipped refills (8,388,608 samples) between every
observed block on both radios. The host queue high-water remained only 1/32. An attempted removal of
the per-refill clock-anchor read did not alter any of those measurements and was reverted in
revision `2219f42c7d7bb2472eaf1e505d48923ff472052b`; the dynamic timing anchors remain intact.
Qualification must therefore choose the largest refill that passes a counter-observable metadata
continuity ladder with at least four kernel buffers. It must reject any rung below 95% observed
coverage; ordinary mask-blind throughput is not sufficient.

Pluto+ Utils revision `cb1d091cd5c5831d0a99347bf74fb4e517800c92` provides that distinct
`radio metadata-ladder` gate. It tests descending refill sizes using the metadata/FPGA-counter path,
requires exact native sample-rate and RF-bandwidth readback, at least four kernel buffers, at least
95% observed device-time coverage, and zero overflow, then reports the largest passing size and
restores the original settings.

The same pinned utility then tested its maximum supported paired-RX frame size, 4,194,304
samples/channel, with four kernel buffers and six timed frames per rung. At 5 MS/s, `.20` delivered
99.56% and `.21` delivered 100.37% of the configured rate; both 2.5 MS/s rungs also kept pace and
both radios restored their original settings. New mixed-rate and ordinary native-bandwidth profile
revisions therefore use `refill_samples=4194304` and `kernel_buffers=4`. Historical profile
revisions remain immutable. Setter acceptance is not by itself a continuity claim: each hardware
canary must still prove counter closure, queue telemetry, and zero-fill integrity.

### Native-rate RF/IF coverage authority

All newly scheduled native-rate legs use analog `bandwidth_hz == sample_rate_hz`: 2.5, 3, 5, and
10 MHz. Historical ordinary profile revisions keep their immutable 2.5 MHz
bandwidth for provenance and reanalysis only; additive `native-bandwidth-v4` profiles replace them
for new ordinary captures. The selected channel and lower/upper edge remain common across both
radios in a mixed dwell, while each leg binds its own rate-appropriate tuner IF and captured
passband.

RF coverage is a hard release criterion, not a display annotation. The 240 MHz occupied-channel
bounds and published edge-pilot IF are canonical contract inputs. The tuner stays
at the pilot-band center whenever the full passband fits in-channel (the 2.5M and 5M cases). A wider
leg moves only the minimum distance inward needed to retain the whole analog passband and the
selected pilot; for example a 10 MHz CH1-lower leg uses 960 MHz IF rather than 959.6875 MHz. Each
capture plan persists the pilot IF, occupied-channel bounds, actual captured IF bounds, analog
bandwidth, and tuner center. Independent contract validation recomputes the exact optimal center as
`clamp(pilot_if, channel_start + bandwidth/2, channel_stop - bandwidth/2)` and requires the entire
geometry to match. The applied radio readback must equal that sealed center, native sample rate, and
analog bandwidth before a V4 recording can publish or become Current. Tests cover every production
channel, both edges, and 2.5/3/5/10 MHz widths. No digital resampling or unrecorded frequency
inference is permitted.

Before enabling each class, run a bounded remote campaign (combined duration at most 30 minutes)
against only `.20` and `.21`:

1. Read-only interface/capability and link-speed verification through pinned Pluto+ Utils.
2. One short transport probe with no publication.
3. One 60-second device-axis capture with alternating high-rate radio assignment.
4. Exact checks: full logical span, verified zero-fill offsets, no overflow, no rejected refill, no
   enqueue failure, queue HWM <=24/32, no writer poison, no kernel/network/RAID error, no swap-in/out,
   >=32 GiB memory headroom, and bounded analysis runtime.
5. Repeat the opposite radio assignment before sealing qualification.

The 2.5/10 schedule weight stays zero and cutover fails closed if any gate fails. A degraded capture
caused solely by verified gaps may remain evidence, but it does not qualify the transport unless the
predeclared observed-coverage floor and every integrity gate pass.

## 5. Test and release gates

Required portable gates:

- immutable contract/parser compatibility for all existing majors;
- 16-slot scheduler property and durable-retry tests;
- fake-radio mixed-rate coordinator tests at 2.5/5 and 2.5/10, including asymmetric gaps,
  cancellation, queue failure, writer poison, terminal gaps, and peer failure;
- V2/V3 same-rate regression and new mixed-manifest storage verification;
- pipeline-plan tamper refusal and real PostgreSQL execution/promotion tests;
- direct 2.5/5/10 scientific equivalence and adversarial no-cross-gap tests;
- radio/paired UTC-intersection and sufficient-stat aggregation tests;
- exact 12-job/98-product/59-PNG browser vertical for both mixed classes;
- release qualification, staged cutover, resource-capacity, systemd, Ruff, format, mypy, and
  diff-clean gates.

Release procedure:

1. Commit and push an exact SHA to `main`.
2. Stage and validate the sealed release without changing live selectors.
3. Seal the native-bandwidth ordinary 2.5/3/5 and mixed 2.5/5 hardware qualification receipt.
   Keep both 2.5/10 and 2.5/15 disabled unless a future transport change makes their exact ladders
   and full recorder campaigns pass.
4. Deploy with capture paused; verify schema, units, workers, BLAS/OpenMP/MKL=4, and no restarts.
5. Run one direct 2.5/5 canary, re-pause, drain analysis, and verify all products/PNGs/API/UI.
6. Run one direct 2.5/10 canary only if its receipt passed, re-pause, drain, and verify likewise.
7. Enable scheduler weights only after both canaries pass. Otherwise enable only the qualified
   2.5/5 feature and leave the 10M slots disabled, never silently substituting another dwell.

## Definition of done

- The production policy is exactly six mixed 2.5/5, two mixed 2.5/10, and eight ordinary intents
  per completed 16-slot cycle. Until 10M passes hardware qualification, deployment uses the
  explicitly versioned safe policy containing six mixed 2.5/5 and ten ordinary intents. Fifteen
  MS/s remains a separate disabled authority and is never silently substituted into either policy.
- Both radios share one selected channel/edge in every mixed dwell and high-rate roles are balanced.
- Every leg uses the maximum native-rate analog bandwidth, persists its exact IF/passband geometry,
  remains wholly inside the selected 240 MHz occupied channel, and retains the selected edge pilot.
- Requested and applied center frequency, native sample rate, and RF analog bandwidth close exactly;
  any driver clipping, quantization, or stale readback fails capture publication before analysis.
- Restart/retry reproduces the byte-identical persisted intent.
- Every mixed capture has a verified fixed logical device axis, correct physical zero fill and
  validity evidence, the maximum qualified 4,194,304-sample refill with four kernel buffers, and no
  hidden packed-axis or resampling path.
- Both mixed classes complete the exact native Standard graph at their captured rates and seal the
  expected 12 jobs, 98 products, and 59 PNG artifacts.
- The production browser displays the same artifact inventory and semantics as the same-rate
  2.5/3/5 pipeline, with gaps represented only in plots and coverage—not as a UI validity table.
- Release, hardware, PostgreSQL, scientific, deployment, API, and browser receipts all bind the
  deployed commit.
- No reboot or local-radio access occurs. After the safe 2.5/3/5 plus mixed 2.5/5 canaries pass,
  acquisition is explicitly resumed with only that qualified pool; if any gate fails it remains
  paused and the failing evidence is retained.
