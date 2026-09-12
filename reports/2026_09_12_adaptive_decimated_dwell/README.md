# Single-RX 10M recording / 2.5M decision engine: implementation checkpoint

2026-09-12. Stage 1 of the deployment plan is implemented as a research replay,
but **the on-radio real-time gate has not passed**. No adaptive profile activation,
corpus migration or firmware-image change has occurred. The user-selected radio
is now `.17`, serial `104000bac4950008230026001b440a003a`; earlier `.20` results
below are historical evidence. The live [replacement-radio checkpoint](../2026_09_12_radio003a_scanner_switch/README.md)
and [RF ledger](rf-ledger.json) supersede the older rollout status and remaining
allowance quoted below.

The larger 262,144-sample refill sustained approximately 65 seconds without a
reported gap, then exposed a duplicate restoration check that incorrectly treated
AGC gain observations as configured gains. PPU `7c382988` now uses its existing
settable-state predicate and retains both gain observations in its receipt.
Manual gains, rate, bandwidth, LO, channel selection, modes and Fast Lock
deactivation remain checked. The recheck on sealed Leo release `eefcb4f0` passed:
65.0196636 seconds of device span, 95.4172% duty, zero missing samples, overflows
or event gaps, and successful cancellation/restoration. This release and block
size are now selected for the fixed production scanner.

The normal 23:20 fixed scan then completed on its first attempt at 95.4264% duty,
with zero reported loss and successful restoration. Native analysis processed all
2,386 visits; Chromium verified all three plots against their manifest hashes.
The full adaptive deployment gate remains open.

## Latest deployment checkpoint

Additional ARM experiments preserve the full six-window screen and one blind
confirmation. None passes the 90 ms mean / 100 ms p99 service-time gate:

| Candidate | Filter mean CPU ms | Pipeline mean / empirical p99 wall ms |
| --- | ---: | ---: |
| Integer FIR, smaller transposed tiles | 62.27 | 120.69 / 123.79 |
| Recursive polyphase filter | 111.35 | 170.76 / 175.13 |
| Recursive filter, two-sample lookahead | 95.21 | 153.84 / 158.63 |
| FP32 FIR, preconverted coefficients | 152.39 | 210.54 / 213.17 |
| Direct 161-tap FIR via FP32 FFT overlap-save | 306.01 | 364.82 / 370.61 |

The recursive candidate preserves the frozen amplitude-response bounds, but has
frequency-dependent phase and changes development positives to cases 2 and 10.
It is not a scientifically qualified substitute. Its ARM arithmetic differs
from the independent FP64 recurrence reference by at most 1 LSB in these cases.
The FFT experiment computes the same direct FIR and retains its four positive
development cases, but is much slower. It uses an isolated static single-precision
NEON build of the existing FFTW 3.3.10 source; production libraries are unchanged.
All new measurements still use the same sixteen development dwells, not holdout.

For an architecture comparison, the unchanged complete pipeline on the host
measures **19.28 ms mean / 27.27 ms empirical p99** with the longer direct FIR,
and 14.85 / 19.22 ms with the compact cascade. Both match integer convolution
exactly. These are saved-data microbenchmarks, excluding transport and feedback;
they do not qualify a host feedback architecture. A user preference is pending
between full coverage on the host, explicitly reduced probes on the radio, and
continued full-coverage radio optimization. No architecture switch is implied.

Current research tests: **41 passed**, including seven explicitly FFTW-marked
overlap-save tests covering full scale, reset, causal boundaries and partial
blocks. Ruff passes. The explicit test installation is selected through
`FFTW_FLOAT_PREFIX`; missing FFTW is a test failure rather than a silent skip.
Existing PPU persistent/adaptive stream and IIO tests also pass: **124 tests**.

### Baseline capture qualification

The preserved [daemon log](baseline-gain-coverage-daemon.log) identifies one
actual ESTALE mechanism: frame `[2403964824731,2403964955803)` had no overlapping
gain observation. Polling once per DMA block leaves insufficient margin for
sampler jitter. libiio `10e72e8b3e8c4e4d62067d2d1d21ef365b6c8fcf` caps the
queued-hop observation interval at half a block and retains strict coverage
validation. It does not manufacture gain/RSSI observations.

The first canary invocation failed before remote staging because source
provenance was mistakenly supplied as a companion-bundle manifest. It collected
no RF. After correcting that invocation, the polling candidate failed on its
first valid visit: 21,050 of 1,200,000 requested samples were absent at the start.
The [failure diagnostics](metadata-canary-startup-failure.json) attest radio
restoration. No subsequent RF canary was started. The [RF ledger](rf-ledger.json)
conservatively charges the entire 9.285-second capture call, including bufferless
setup and cleanup, against the 1,800-second qualification limit. Four canaries
and the first scheduled qualification reserve 1,500 seconds; the remaining
unallocated allowance is approximately 290.7 seconds.

Inspection found that hopping began immediately after buffer allocation, before
any validated DMA frame. libiio `26310f8` adds an optional ARMED phase and defers
the first recall until timestamp, gain and RSSI validation succeeds on the first
frame. Existing wire layouts are unchanged. Both fixed and adaptive lifecycles,
legacy immediate start and cancellation are covered by native tests. Nine native
tests and an ARM build pass; the sealed candidate is recorded in
[provider provenance](startup-provider-provenance.json). This closes a startup
ordering hole but has not been qualified live and is not a proven explanation
for every observed failure.

The fixed production scanner separately reported COUNTER_DISCONTINUITY at
21:26:28 and 21:41:49 UTC. Its 21:40 retry completed at 21:47:12. Neither new
provider fix has been deployed to the scheduled service, and neither establishes
that the later counter gaps are solved. Further diagnosis must preserve actual
expected/observed counters. Successful retries do not satisfy reliability gates.

## Implemented and tested

- Bounded causal factor-four decimation of one RX CI16, with direct and cascaded
  FIR candidates. Q15 coefficients, exact integer accumulation, rounding ties
  toward positive infinity and saturation at each stage. Absolute coefficient
  sums are bounded to prevent signed accumulator overflow at full input scale.
- The most effective optimization keeps both stages in small cache-sized tiles,
  carrying the exact input history across tiles and resetting only at a new dwell.
  Physical RX extraction remains outside this research entrypoint; no production
  receiver-binding or transport qualification is implied.
- The existing 2.5M worker screens all six temporal windows and performs one blind
  ranked confirmation. Thresholds and native detector build flags remain fixed.
  No progressive six-confirmation policy is used on negative dwells.
- Standalone replay builds use the production ARM FFTW library, source hashes and
  binary receipts. Each invocation is limited to 64 cases, 100 seconds wall time,
  85 seconds CPU and 160 MiB address space; it opens no IIO interface.
- Twelve component tests cover response, full-scale integer parity, history reset,
  invalid geometry, impulses across tile boundaries and short/final partial tiles.
  Together with the earlier research suites, 28 tests pass. Ruff also passes.

## Filter candidates

| Candidate | FIR design | Native group delay |
| --- | --- | --- |
| Direct | 161 taps, 1 MHz cutoff, Kaiser beta 7.5 | 80 samples / 8 us |
| Cascade | 19-tap halfband at 10M, then 81 taps at 5M with 1 MHz cutoff; beta 7.5 | 89 samples / 8.9 us |
| Compact cascade | 15-tap halfband, beta 6.75; then 47 taps at 5M, 1 MHz cutoff, beta 5.75 | 53 samples / 5.3 us |

The compact cascade's quantized linear response has less than 0.01 dB deviation
through 800 kHz and more than 65 dB rejection from 1.25 to 5 MHz. These limits
were checked before holdout evaluation. Clipping and quantization make the actual
integer system nonlinear; frequency response alone is not detector qualification.
Decimation phase is zero in these replays. A production decision binding must
still specify phase, group delay, unsupported startup samples and final support.

## ARM development measurements

Sixteen saved development dwells reuse the earlier selection balanced across
RX0/RX1, lower/upper edge and the earlier 5M six-confirmation reference outcome.
They are neither a holdout nor a representative population mix. The radio was
idle between scheduled scans for every replay. IQ input streaming and component
parity checks are outside reported DSP timing; extraction/IPC/capture contention
and a paced queue are not represented. These results cannot prove live capacity.

| Implementation | Filter mean CPU ms | Complete pipeline mean / empirical p99 wall ms |
| --- | ---: | ---: |
| Initial cascade, four outputs per vector loop | 159.70 | 216.70 / 221.11 |
| Cascade, sixteen outputs per loop | 120.56 | 176.61 / 180.12 |
| Cascade, transposed input phases | 110.17 | 168.24 / 173.69 |
| Direct filter, transposed phases | 125.56 | 182.79 / 189.22 |
| Compact cascade, transposed phases | 88.58 | 147.05 / 150.29 |
| Compact cascade, cache-sized tiles | 62.16 | 121.31 / 124.74 |
| Symmetric pair sums | 73.77 | 131.44 / 134.13 |

FP32 and generated unrolled kernels were also measured; neither improved on the
tiled integer candidate. The final source retains the tiled integer path as the
default. The machine-readable summary includes these experiments and the final
source-bound rerun. An empirical p99 from sixteen cases is not a population-tail
estimate. The mean already fails the proposed 90 ms mean / 100 ms p99 gates.

The final source-bound rerun was worse: **148.71 ms mean / 206.07 ms empirical
p99 wall time**, with 68.61 ms mean filter CPU. It ran between captures, but
wall-time contention was not controlled. Retain this result alongside the best
earlier run; do not use the best run as evidence of repeatable real-time capacity.

Every tested integer output matches independent integer convolution exactly.
All repeated implementations of a given filter preserve the same positive versus
non-positive development outcomes; exact selected-window/candidate parity has
not been established. The compact filter produces three positive dwells, versus four for the
longer cascade/direct candidates. That difference needs scientific investigation;
the original selection's eight 5M-reference positives are not RF ground truth.
No quality-equivalence claim is made for changing filter coefficients.

## Controls and limits

The final default ARM binary passes 22 synthetic/arithmetic controls: all twelve
injected pilot cases are positive (both edges, all six windows), and all ten other
controls are non-positive. Filtered output is bit exact even for full-scale random
input and positive/negative saturation controls. Desktop sanitizer replay also
passes. These controls are a smoke test, not false-alarm calibration or held-out
RF sensitivity. The independent holdout selection is frozen in
[`qualification-protocol.json`](qualification-protocol.json) and has not been
evaluated. No paced 300-second or live shadow qualification has been attempted.

## Production baseline finding

While leaving the existing fixed scanner running, acquisition logs showed
`OSError: [Errno 116] Stale file handle` during metadata-aware refill at 20:05:01
and 20:41:00 UTC. The latter was the first 20:40 attempt; its automatic retry
subsequently completed. The 20:20 slot also had three early failures requiring
separate diagnosis. Research ARM runs did not overlap these captures.

At that initial checkpoint the error's origin was not established. The later
daemon capture above resolves one gain-coverage failure; separate counter gaps
remain open. Do not describe ESTALE alone as proven IQ loss or storage failure.
Terminal diagnostics for the two refill errors attest restoration. Baseline
capture reliability remains a gate before adaptive deployment.

## Next work toward deployment

The full implementation/deployment goal remains active. Investigate a causal
decimator requiring fewer operations while retaining native 10M recording and
complete six-window screening. If another filter topology is used, qualify its
phase response, boundaries and native-counter mapping explicitly. Existing seeded
confirmation experiments are not quality-equivalent replacements for the blind
worker; they must not be substituted merely to lower timing numbers.

Resolve the production refill diagnostics in parallel with this feasibility work.
Provider/storage/analysis/UI integration, bounded live canaries, release switching
and browser verification remain outstanding. Keep the fixed profile selected;
neither numerical correctness nor successful automatic retries satisfy the
adaptive deployment gates.
