# Radio .20: loaded ARM acquisition at 30 and 60 MS/s

Both FPGA profiles now deliver continuous IQ while the radio's ARM runs blind
acquisition, full timing/frequency resolution and retained-IQ catch-up. The
physical tests below established loaded capture and candidate rejection, with
no supported native handoff. Autonomous scanning, tracking and refinement are
still unfinished.

The target is `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`.
The bounded runtime was introduced in firmware-worktree commit
`5ed9429269cc2a53c4b133c063dcdc0eb718b232`. It follows the
[native commissioning](2026_09_12_radio20_native_30_60_commissioning.md) and
[saved-IQ ARM benchmark](2026_09_12_radio20_cpu_acquisition_catchup.md).

## Loaded physical measurements

Each run retained 25,165,824 complex samples at 2.5 MS/s: 10.0663296 seconds
of RF, with 1,536 returned buffers. Both baseline runs used receive LO
1,690,312,496 Hz, 2.5 MHz RF bandwidth, manual gain 30 dB and A_BALANCED.

| Native FPGA rate | ARM coarse scan | ARM resolution/catch-up | Maximum refill interval | Supported handoffs |
| --- | --- | --- | --- | --- |
| 30 MS/s | 675.68–759.77 ms | 610.77–613.63 ms | 6.699 ms | 0/6 |
| 60 MS/s | 678.24–765.85 ms | 594.07–606.71 ms | 6.856 ms | 0/6 |

Both complete captures had zero active-epoch CDC or pacer drops. Independent
replay checked all 439,956 coarse-grid values, 204 resolver hypotheses, 96
integer moment sets and 476,592 worker IQ samples against the retained capture
bytes. All agreed. Native journals contained only their headers: no native
descriptors or measurements were produced.

A separate 60-MS/s revisit at LO 1,440,312,500 Hz also retained a complete
10.0663296-second capture with zero drops and six reported unsupported
candidates. Its maximum refill interval was 11.545 ms. That run has a
continuity review; its complete worker arithmetic was not independently
replayed. These three captures total 30.1989888 seconds of new RF.

## Where the work runs

| Component | Location | Sample rate / cadence | Current evidence |
| --- | --- | --- | --- |
| Source counter and channel extraction | FPGA | 30 or 60 MS/s → 2.5 MS/s | Continuous export under ARM load at both rates |
| Retained-IQ ring and blind search | ARM | 2.5 MS/s; 14,000 samples/search | Two scan threads; two-second ring; six fresh attempts per run |
| Resolution and catch-up | ARM | 2.5 MS/s; 3,300 samples/pilot; 750 Hz nominal repetition | Full resolver and past-pilot checks ran against advancing source time |
| Scheduled measurements | FPGA | 30 or 60 MS/s; 39,600 or 79,200 samples/pilot | Earlier arbitrary scheduled jobs passed; new acquired jobs still unverified |
| Prediction and native feedback | ARM | Native source coordinates; 750 Hz measurement cadence | Composed in the executable; physical acquired feedback still unverified |

REBASE occurs after capture starts. Its native counter defines the new epoch's
boundary; older signal-center samples remain in the recording but are excluded
from the worker's ring. Finite capture completion deliberately invalidates the
epoch. The operator verifies drained results before clearing it.

## Candidate selection findings and follow-up

Offline review of all eight retained candidates per window found a useful
exception in the 60-MS/s baseline: window five's second-ranked candidate had
four-pilot power coherence 0.049286. The runtime had examined only the top
coarse candidate. A diagnostic search around the second candidate found 90
individual pilots above 0.05 among 976 examined repeats, with peak coherence
0.066710. These per-pilot searches are diagnostic fits, not validated causal
history or a tracking lock. They justify investigating candidate ordering;
they do not justify lowering the support gate.

The corresponding all-candidate original-pilot reviews at 30 MS/s and the
1.4403125 GHz revisit remained weak: maximum four-pilot coherence 0.001907
and 0.002094 respectively. Failure to find support in these selected windows
does not establish that an entire recording lacks the signal.

The follow-up implementation ranks the eight coarse basins using one full
original pilot and one FFT per basin before invoking the unchanged resolver
and catch-up gates. It also rereads the native counter to select a future batch
from the same retained history and unchanged forecast horizon. A stale original
handoff therefore need not discard an otherwise still-valid later prediction.
The controller continues to check hardware time after descriptor retention.

This follow-up is firmware-worktree commit `f4bd5d984`. Its bounded deployment
to the resident 60-MS/s image is retained in `cpu-live60-ranked-v1/`. All
25,165,824 samples arrived with zero CDC/pacer loss. Ordering eight basins added
65.89–66.47 ms; total scan-plus-order time was 749.33–828.31 ms, with measured
seed ages 753.03–831.74 ms. Resolution/catch-up took 600.89–609.43 ms.
The maximum refill interval was 7.044 ms. All six newly selected candidates
failed support, so no native descriptor was submitted.

Independent replay checked its 219,978 grid values, all 48 new ordering scores,
102 resolver hypotheses, 48 moment sets, 238,296 worker IQ samples and source
epoch binding. This qualifies the added ordering cost and rejection path at
60 MS/s. The four loaded captures together total 40.2653184 seconds of RF.

The same executable subsequently passed the 30-MS/s loaded rejection test in
`cpu-live30-ranked-v1/`. It retained all 25,165,824 samples with zero active
CDC/pacer loss. Scan-plus-order took 824.55–836.97 ms, including 66.27–68.19 ms
for ordering; seed ages were 831.70–838.24 ms. Resolution/catch-up took
609.25–614.88 ms, and the largest refill interval was 8.758 ms. All six
candidates failed support. The independent review checked the same complete
grid, ordering-score, resolver, IQ and integer-moment counts as the latest
60-MS/s run. This closes physical validation of loaded candidate ordering at
both rates; it does not qualify acquired native feedback.

The 30-MS/s boot had 5,415,779 pre-epoch pacer drops at its default receive
clock. After exact-rate configuration and calibration, REBASE established the
qualified epoch with zero drops. The review preserves the boot counters
separately; the runtime must configure the rate before opening a fresh epoch.

A separate saved-IQ quality diagnostic passed window five's stronger
second-ranked candidate through the actual C worker at nine frozen receiver
snapshots, from 100 to 950 ms after its search window. At 100 ms it supported
six of the required eight initial observations; later snapshots supported at
most one. All nine rejected handoff. This demonstrates why finding a stronger
candidate is insufficient by itself, without treating frozen-snapshot replay
as live timing evidence. Quality thresholds and required history remain unchanged.

Two additional 30-MS/s visits used the configured upper edges of channels 4
and 1. Each retained another 10.0663296 seconds with zero active-epoch drops:

| Receive LO | Complete retained samples | Largest refill interval | Supported initial history |
| --- | --- | --- | --- |
| 1,940,312,500 Hz | 25,165,824 | 7.301 ms | Zero in each of six attempts |
| 1,190,312,500 Hz | 25,165,824 | 6.994 ms | Three in the sixth attempt; zero in the other five |

At 1,190.3125 MHz, the sixth candidate had original single-pilot power
coherence 0.069904 and resolved four-pilot coherence 0.056742, at receiver-relative
CFO +438,250.84 Hz. Three supported catch-up observations were insufficient for
the required eight, so the worker rejected handoff and submitted no native jobs.
Both visits have complete independent IQ, grid, ordering, resolver and moment
reviews. The initial review helper assumed rejected attempts had zero supported
history; it stopped on the three-observation case. Its correction preserves and
checks partial history rather than treating rejection as absence of support.
Both reviewer versions are retained by hash. No runtime gate changed.

These three new 30-MS/s captures add 30.1989888 seconds of RF. The seven
loaded captures documented here total 70.4643072 seconds. Channel visits occurred
at separate times, so they do not provide simultaneous coverage or establish
the absence of usable signals on any band.

An additional operator check, committed as `02027ea3d`, requires a drained,
cleared GLT1 snapshot before changing RF settings. This preserves unread heads
left by a prior failed run. Historical boot drop counters are recorded separately
from loss in a fresh tracking epoch.

The current relevant tests pass: 15 runtime/composition tests and 16 operator
admission tests. Generated advancing-IQ tests retire 1,500 simulated native
measurements at both rates; they also cover candidate ordering, cancellation,
source loss, publication lag, exhausted prediction horizon, retention failures
and late submission. Simulated native results are not physical RF evidence.

## Retained evidence

Compact reviews are in [the accompanying JSON](figures/2026_09_12_radio20_loaded_30_60_tracking/evidence.json).
Full artifacts remain under
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`, in
`cpu-live30-v2/`, `cpu-live60-v2/` and `cpu-live60-lo1440-v1/`.
The 60-MS/s deployment receipt is
`deploy60-live-v1/receipts/19eddb0f-bef5-403d-80bc-8b66e81f66a1.json`.
The subsequent verified 30-MS/s transition is
`deploy30-ranked-v1/receipts/131d1226-2cd8-4564-9c69-4228ea150046.json`.
The latest captures are `cpu-live30-ranked-v1/`,
`cpu-live30-ranked-lo1940-v1/` and `cpu-live30-ranked-lo1190-v1/`.
The two `.20` attempts refused by the shared radio lease collected no RF.

After the latest run, `.20` remained on `glrt-iq-tracking-r30000000-v1`, boot
`f6f290d1-21ff-4a31-bb88-3ccbb46f488b`, at receive LO 1,190,312,500 Hz.
The operator verified unchanged RF settings, TX powerdown, idle buffers,
drained/cleared tracking state and removal of its temporary executable files.
This is a bounded test deployment; an autonomous startup service is not installed.

Completion still requires an acquired, supported native feedback loop at both
rates, followed by the authorized scanning/reacquisition and refinement work.
