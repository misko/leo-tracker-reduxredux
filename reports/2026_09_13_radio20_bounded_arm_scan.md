# Radio .20: live ARM acquisition reaches native FPGA measurements

A live 60-MS/s run on `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`, reached the FPGA from a fresh ARM
acquisition. Attempt 98 evaluated 116 past pilots, accepted 114 and retained
96 supported observations. It produced a fresh handoff proposal in 1.385 seconds,
then submitted and retired ten complete native measurements. All ten failed
the unchanged coherence gate, so the controller stopped at its forecast horizon.
This is a verified live handoff with unsuccessful native tracking, not a
qualified autonomous tracking system.

The resident image remains `glrt-iq-tracking-r60000000-v1`, boot
`89459b01-4aeb-4ad1-a01b-4fe065b8ea76`. This follows the
[original-epoch startup and ARM acceleration](2026_09_13_radio20_original_epoch_startup.md)
work. Earlier [30/60-MS/s commissioning](2026_09_12_radio20_native_30_60_commissioning.md)
remains the physical evidence for both FPGA rates; the new selected-window
profile has been tested on fresh RF at 60 MS/s only.

## Bounded scan implementation

Firmware-worktree commit `2bc9ac6d66a98059943330ee8d7ce7bfe22eae21` adds the
explicit `--blocks 45000` profile. It permits at most 200 acquisition attempts
or 294.912 seconds, while retaining the searched windows instead of the entire
raw-IQ stream. It maintains the existing two-second ring and preserves all
support, freshness and forecast limits. Capture stops when the worker ends,
including on a native-controller failure.

| Component | Input rate | Retained evidence |
| --- | --- | --- |
| FPGA receive path | 60 MS/s in this run; 30 MS/s also supported | Source counters and 2.5-MS/s exported IQ |
| ARM capture thread | 2.5 MS/s | Every returned-buffer counter and a two-second IQ ring |
| ARM coarse acquisition | 2.5 MS/s, 14,000 samples per search | Exact searched IQ, complete integer grids and eight candidate scores |
| ARM resolution and catch-up | 2.5 MS/s | Four-pilot resolver inputs and each evaluated past pilot |
| FPGA native measurements | 60 MS/s, 79,200 samples per pilot | GLT1 integer moments, source association and completion counters |
| ARM native controller | Native source coordinates, 750-Hz pilot cadence | Descriptors, estimates, handoff history and drain/clear journal |

Searched IQ is capped at 11.2 MB and worker IQ at 80 MB. The private evidence
filesystem remains 320 MiB, with separate memory and filesystem preflights.
Uncertain execution or incomplete retrieval preserves the remote evidence.
The two shorter profiles still record their full IQ streams.

All 110 relevant component and operator tests passed. They include synthetic
1,500-measurement handoffs at both rates, exact searched-IQ association,
retention failure, finite budgets, and early-stop counter/tail checks. The ARM
build passes with warnings treated as errors. These tests are separate from
physical RF evidence.

## Actual live result

The receive settings were LO 1,190,312,500 Hz, 2.5 MHz bandwidth, manual gain
30 dB and A_BALANCED. The run ended after 112.9523984 seconds of exported-sample
duration, well before its limit. It returned 282,378,240 complex samples;
final counters include an additional 2,756 exported samples at shutdown.
Full raw IQ was intentionally not recorded. The retained search and worker IQ
contain 1,372,000 and 4,248,568 complex samples respectively.

Independent review passed source-counter continuity with zero active-epoch CDC
or pacer drops, 3,592,974 coarse-grid values, 784 ordering scores, 1,666 resolver
hypotheses, and 892 integer-moment/dense-fit comparisons. It also checked
1,802,419 overlapping retained samples for exact consistency. Source association
outside those overlaps relies on the recorded, component-tested owned views;
unretained IQ cannot be revisited. Maximum refill interval was 9.067 ms.

The first 97 attempts rejected without supported history. Attempt 98 had a
single-pilot ordering score of 0.072420. Its scan plus ordering took 531.962 ms;
resolution and catch-up brought total startup to 1,384.927 ms. The final proposal
had 14,514 coarse samples, or 5.806 ms, of lead over its checked source counter.
The actual hardware-counter preflight then selected the native batch.

## Why native tracking stopped

The native journal contains ten complete, correctly associated measurements at
frames 1049–1058. The last supported coarse observation was frame 1026, so frame
1058 was exactly the unchanged last-supported-plus-32 limit. Every native
estimate had rejection bit 64, low coherence; no new native support extended
that horizon. The controller returned `GLRT_NATIVE_ACQUISITION_LOST` (-4),
drained all ten heads and cleared its state. The executable and operator
correctly reported failure.

A separate numerical review reconstructed the rate-specific reference basis
and recomputed the local fits from the retained native moments. All reported
corrections, coherences and rejection decisions matched. This verifies the
moment-to-estimate calculation; native raw IQ was not retained, so it does not
independently recompute the FPGA's native moments for this event.

| Diagnostic | Last three supported coarse observations | Ten native observations |
| --- | --- | --- |
| Power coherence | 0.0581–0.0616 | 0.0305–0.0386 |
| Rotated IQ energy per complex sample | 204–214 | 406–420 |
| Local native correction | Not compared here | Delay within 19.4 ns; residual frequency within 46.6 Hz |

These are nearby observations at different sample rates and times. The energy
and coherence difference suggests testing the effect of filtering, while
fading and reference differences remain possible explanations. It does not
justify weakening the native support gate. The next diagnostic should retain
coarse IQ covering the same pilots as the native measurements, so their signal
power, total energy and timing can be compared directly.

The operator retrieved every artifact, verified unchanged firmware/boot and
TX-safe idle state, and removed its private filesystem. Because the executable
returned failure, this operator version exited before its separate post-capture
RF-setting comparison. The receipt records that limit; no claim of that check
is made.

## Relevance and remaining work

This run establishes that fresh live ARM acquisition and retained-IQ catch-up
can reach native FPGA submission without a host acquisition worker. It also
shows that the bounded evidence design can examine more opportunities without
retaining several gigabytes of raw IQ. Host setup, calibration and evidence
retrieval still use the qualification operator.

Sustained supported native feedback remains unqualified. Autonomous frequency
selection, reacquisition after tracking loss, refinement and an installed
FPGA-plus-ARM service also remain unfinished. A successful handoff at 30 MS/s
still needs its own fresh-RF evidence.

Evidence root:
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.

- `cpu-live60-selected-lo1190-v1/`: actual failed tracking run, selected IQ, journals, source/arithmetic review and native-estimate review.
- `selected-review-test-fixture-v1/`: clearly labeled reviewer test fixture made from an earlier full-IQ capture, with synthetic profile metadata; not new RF evidence.
- `selected-review-test-result-v1.json`: reviewer checks, including rejection of altered grids and worker IQ even after their receipt hashes were updated.
- `review_selected_acquisition.py`, `review_selected_native.py`: read-only review sources.

The checked-in [evidence manifest](figures/2026_09_13_radio20_bounded_arm_scan/evidence.json)
retains the actual operator and review records, implementation identity and
artifact hashes. A numerical-review pass does not change the failed run into
a successful tracking qualification.
