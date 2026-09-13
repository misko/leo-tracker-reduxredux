# Radio .20: resolve the measured epoch before catch-up

The radio's ARM now reaches a fresh handoff proposal on IQ from the current
30-MS/s experiment: 146 past pilots evaluated, 137 accepted, and a 96-observation
rolling history in 1.742 seconds. The proposal remained 6.068 ms ahead of the
last checked paced source counter. A control rejected. This is an actual ARM
saved-IQ replay, not a fresh-RF acquisition-to-native-feedback qualification.

The target remains `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`. The ARM replay checkpoint used
`glrt-iq-tracking-r30000000-v1`, with boot ID
`f6f290d1-21ff-4a31-bb88-3ccbb46f488b`. The subsequent live follow-up below
also tested 60 MS/s; that is now the resident image.
This follows the [loaded 30/60-MS/s tests](2026_09_12_radio20_loaded_30_60_tracking.md)
and [historical paced ARM replay](2026_09_13_radio20_paced_arm_startup.md).

## New RF and the storage limit

The longer qualification profile allows 4,096 refills of 16,384 complex
samples, or 26.8435456 seconds at the exported 2.5 MS/s. It makes at most
16 acquisition attempts. The default remains 1,536 refills and six attempts.

| Receive LO | Retained complex samples | Result | Acquisition result |
| --- | ---: | --- | --- |
| 1,190,312,500 Hz | 62,912,512 | Retained-IQ write failed before the planned end | All 16 attempts rejected; no native jobs |
| 1,690,312,496 Hz | 67,108,864 | Complete 26.8435456-second capture | All 16 attempts rejected; no native jobs |

Both used native 30 MS/s, 2.5 MHz RF bandwidth, manual gain 30 dB and
A_BALANCED. The first attempt checked available RAM but missed the independent
tmpfs capacity limit: `/tmp` has 253,436 KiB total capacity, less than the
256-MiB planned IQ file. Its final source counters report 62,917,598 exported
samples; 5,086 of those samples were not retained. This remains a failed
capture even though the retained acquisition calculations passed review.

The operator now mounts a private, bounded 320-MiB tmpfs at the longer run's
unique evidence directory. Before RF configuration it separately checks RAM
for the full IQ file plus 80 MiB of headroom, and filesystem capacity for IQ
plus 40 MiB of journals, worker IQ, grids and payloads. Cleanup requires a
terminal process, retrieved artifacts and idle-radio attestation before
removing its files and unmounting that filesystem. Uncertain execution or
incomplete retrieval preserves the evidence.

The second capture passed both checks and retained every sample. Its largest
returned-buffer interval was 7.441 ms. Scan plus ordering took 749.13–832.59 ms;
resolution and initial catch-up took 602.03–609.66 ms. Independent review found
zero active-epoch CDC or pacer drops in both runs, checked 1,173,216 grid values,
256 ordering scores, 544 resolver hypotheses, 256 integer moment sets and
1,270,912 copied worker samples. The radio returned idle with TX disabled and
the private mount was removed. These runs add 52.0105848 seconds of
exported-sample duration, including the failed capture's unretained tail.

## What the denser saved-IQ search found

A bounded offline scan revisited the recordings every 50 ms, using the same
14,000-sample coarse search and eight full-pilot ordering FFTs. In the partial
1.1903125-GHz recording, 32 of 504 windows had an original single-pilot power
coherence at least 0.05; the maximum was 0.088815. None of the 537 windows at
1.690312496 GHz reached that value; its maximum was 0.016139. A historical
positive slice had 10 such windows out of 50, with maximum 0.082686.

Those scores are exploratory candidate evidence, not accepted tracks or a
signal-absence test. A single full-pilot match does not establish continuity.
The stronger sequence between 8.15 and 21.95 seconds in the 1.1903125-GHz
recording shows roughly 13 coarse samples/second of average timing motion and
about -3.6 kHz/second of carrier change. These are diagnostics from selected
matches, not calibrated Doppler, satellite identity or PSS timing truth.

## Startup correction

The previous CPU seed planner advanced a delayed candidate to the first four
of the latest 64 nominal repeats before resolving timing. At an observed seed
age near 0.83 seconds, that moved the seed about 0.75 seconds beyond the
measured candidate. A 15-sample/second timing drift moves the real pilot by
about eleven samples in that interval, beyond the resolver's +/-8-sample guard.

The updated planner resolves four pilots at the original measured candidate
epoch, then follows supported past observations through retained IQ. It rejects
overwritten original samples. The one-second proposal-age limit, two-second
ring/source budget, 200-observation cap, eight initial supported observations,
0.05 coherence gate and last-supported-plus-32-frame forecast horizon remain.

| Selected saved-IQ cohort | Previous seed policy: fresh proposals | Original-epoch seed: fresh proposals |
| --- | ---: | ---: |
| Eight stronger current windows, at least 0.5 s apart | 0/8 | 3/8 |
| Four current weak controls | 0/4 | 0/4 |
| Eight historical accepted windows | 5/8 | 7/8 |
| Four historical rejected controls | 0/4 | 0/4 |

These comparisons use the actual C worker with explicitly modeled costs:
840 ms for acquisition and ordering, 600 ms for resolution, and 2.5 ms per
past pilot. Successful original-epoch runs evaluated 152 past pilots and
reached a proposal at 1.820 seconds. These selected development cohorts are
not independent or representative detection-performance measurements.

## Actual ARM result and handoff race

The first actual ARM replay with the original-epoch seed accepted 136 of
145 past observations, but returned STALE after 1.738 seconds. An IQ publication
advanced the source counter while the handoff history was being journaled:
the proposed lead changed from 14,884 samples to -1,228 samples. The final
freshness check correctly prevented READY.

The worker may now re-enter causal scheduling once after such a stale
proposal, retaining the same supported history and frame ordinals. Every
proposal must still pass a source check after retention. A second stale
proposal rejects. Component tests force both a recoverable publication race
and repeated lateness; cancellation, source loss and retention failures still
prevent handoff.

| Actual ARM replay | Past evaluated / accepted | Elapsed | Final proposal |
| --- | ---: | ---: | --- |
| Before bounded refresh | 145 / 136 | 1.738 s | Stale, rejected |
| Updated worker | 146 / 137 | 1.742 s | READY, 15,169 coarse samples / 6.068 ms lead |
| Updated worker, control | 8 / 0 | 1.406 s | Rejected, no proposal |

Independent review checks exact retained IQ, complete coarse grids, all
ordering scores, all 17 resolver hypotheses, integer moments, dense real-SVD
fits, acceptance decisions, rolling history and final forecast bounds. For the
updated positive and control it checks 73,326 grid values, 16 ordering scores,
34 hypotheses, 154 moment/SVD fits and 534,832 copied IQ samples. One handoff
record was retained in the successful ARM run; the forced-refresh branch is
specifically covered by component tests. These replays open no RX buffer and
submit no native job. Firmware, boot, TX and idle state match before and after.

## Corrected live startup at both native rates

After the initial admission refusal, the corrected executable completed one
26.8435456-second live capture at each native rate. Both used receive LO
1,190,312,500 Hz, 2.5 MHz RF bandwidth, manual gain 30 dB and A_BALANCED.
Each retained all 67,108,864 exported complex samples and made 16 attempts.

| Native rate | Scan plus ordering | Resolver / initial catch-up | Maximum refill interval | Supported history / acquired native jobs |
| --- | --- | --- | --- | --- |
| 30 MS/s | 820.56–831.56 ms | 601.65–607.96 ms | 7.454 ms | One observation in one attempt; zero jobs |
| 60 MS/s | 750.15–833.41 ms | 607.20–615.52 ms | 10.765 ms | Zero supported observations; zero jobs |

Both captures had zero active-epoch CDC and pacer drops. Independent review
checked another 1,173,216 coarse-grid values, 256 ordering scores, 544 resolver
hypotheses, 256 integer moment sets and 1,270,912 copied worker samples.
Both native journals contained only their headers: acquisition never authorized
native submission. The operator verified unchanged receive settings, firmware,
boot and TX/idle state within each run, retrieved all artifacts, then removed
the private RAM filesystem. This adds 53.6870912 seconds of exported-sample
duration to this report's earlier captures.

The 60-MS/s deployment completed updater, FIT readback, reboot identity and
SSH host-key rotation checks. Receipt
`deploy60-original-seed-v1/receipts/b4d9084a-4e21-4248-8aaa-188dbb53be6f.json`
identifies the same serial and image `glrt-iq-tracking-r60000000-v1`.
The latest verified boot ID is `89459b01-4aeb-4ad1-a01b-4fe065b8ea76`.

The native handoff preflight originally wrote an unrecognized journal kind.
Commit `3a4d751fc` retains the same snapshot using the existing `snapshot`
record, preserving compatibility with journal review and recovery. The actual
composed worker tests now pass their complete simulated 1,500-head journals
through the independent GLT1 reviewer at both rates. The 60-MS/s executable
includes this fix; it changes evidence framing, not acquisition arithmetic.

## Exact ARM vector acceleration

Commit `932fcc20e` uses ARM NEON signed widening products for eight of the
eleven taps in each coarse complex dot product, followed by three scalar
taps. It preserves the exact integer square-root and normalized-score rules.
The complete dot product is bounded to 1,476,395,008 for CI16 samples and
validated CI12 coefficients; SIMD lanes and intermediate reductions therefore
fit signed 32 bits. Portable builds retain the scalar path.

The paired saved-IQ ARM benchmark on the resident 60-MS/s image measured
638.54–645.63 ms per window for the scalar baseline and 456.90–463.46 ms for
NEON: a 28.58% reduction in mean scan time, or 1.400x speedup. Every one of
the 146,652 grid values per implementation and all selected peaks match the
independent integer oracle. Before scanning, the actual NEON executable passed
10,064 component-owned comparisons against wide-integer arithmetic, including
rails and varied input alignment. Twelve host coarse-scanner tests also pass.

The paired benchmark opens no RX buffer and submits no native job. After an
initial lease refusal before radio contact, the vectorized executable also
completed a live 60-MS/s capture at receive LO 1,190,312,500 Hz. It retained all
67,108,864 exported samples over 26.8435456 seconds, with zero active-epoch
CDC or pacer drops and a maximum refill interval of 7.293 ms.

Under live capture load, coarse scanning took 472.28–533.12 ms, or
538.57–599.43 ms including candidate ordering. Resolution and initial catch-up
took 601.39–613.22 ms. All 16 attempts rejected with zero supported history;
no acquired native jobs were submitted. Independent review passed all 586,608
grid values, 128 ordering scores, 272 resolver hypotheses, 128 moment sets and
635,456 copied worker samples. The operator retrieved all artifacts and removed
the private filesystem after idle-state checks. This establishes faster
acquisition computation during capture, while live acquired feedback remains
unqualified. The preceding two-rate table describes the scalar executable;
only the saved-IQ benchmark compares implementations on identical inputs.

## Implementation and remaining work

Firmware-worktree commits are `cc3883329` (long dwell), `82db85843` (private
filesystem and preflight), `52e566828` (original-epoch seed) and `b42683a5e`
(bounded handoff refresh). Component checks passed: 65 seed tests, 48 worker
tests, 24 live-composition tests, 53 operator tests and two saved-benchmark
tests. Reference ROMs and
persisted GLA1/GLT1 contracts were preserved.

The corrected startup has now run on fresh RF at both rates, but no candidate
passed the full history requirement. A supported fresh-RF acquired
native-feedback loop, autonomous scanning, reacquisition and refinement remain
unverified. The existing
30/60-MS/s transport and arbitrary scheduled-job results remain separate
evidence and do not establish this acquired feedback path.

## Retained evidence

Evidence root:
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.

- `cpu-live30-long-lo1190-v1/`: failed capture, retained partial IQ and numerical review.
- `cpu-live30-long-lo1690-v1/`: complete longer capture and numerical review.
- `dense-saved-scan-v1/`: all window scores and best grids.
- `current-ranked-replay-v1/`, `current-original-seed-replay-v1/`: paired current-IQ modeled replays.
- `historical-ranked-replay-v1/`, `historical-original-seed-replay-v1/`: paired historical modeled replays.
- `paced-original-seed-input-v1/`: exact selected positive/control input bytes and manifest.
- `paced-original-seed-arm-v1-results/`, `paced-original-seed-arm-v2-results/`: actual ARM journals and independent reviews.
- `cpu-live30-original-seed-lo1190-v1/`: admission-refused receipt for the updated live executable.
- `cpu-live30-original-seed-lo1190-v2/`, `cpu-live60-original-seed-lo1190-v2/`: complete corrected live captures and independent reviews.
- `deploy60-original-seed-v1/`: successful 30-to-60-MS/s transition and readback/return evidence.
- `coarse-neon-pair-v2/`: actual ARM scalar/NEON grids, timings and independent review.
- `cpu-live60-neon-lo1190-v1/`: admission-refused receipt for the vectorized live executable.
- `cpu-live60-neon-lo1190-v2/`: complete vectorized live capture and independent review.

The checked-in [evidence manifest](figures/2026_09_13_radio20_original_epoch_startup/evidence.json)
retains reviews, source and binary hashes, cohort summaries and operator receipts.
