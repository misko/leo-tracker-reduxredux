# Radio .20: paced ARM startup on historical IQ

The current acquisition and retained-IQ catch-up code reaches a fresh handoff
proposal on radio `.20`'s ARM when given a stronger historical recording with
IQ delivered at 2.5 MS/s. The positive case built 68 supported observations in
1.56 seconds; the selected negative control built none. This closes a startup
timing question left by the [loaded 30/60-MS/s tests](2026_09_12_radio20_loaded_30_60_tracking.md).
It does not establish a fresh RF acquisition or native FPGA feedback loop.

## Actual ARM result

Radio `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`, ran two
bounded replays on its resident `glrt-iq-tracking-r30000000-v1` image. No IIO
receive buffer was opened and no native descriptor was submitted. The source
clock was a paced replay clock derived from ARM monotonic time, not a newly
observed FPGA counter. The stored IQ was originally captured at native 60 MS/s
and exported by FPGA at 2.5 MS/s.

| Measurement | Selected positive | Selected control |
| --- | --- | --- |
| ARM blind coarse scan | 763.51 ms | 733.80 ms |
| Full-pilot candidate ordering | 64.05 ms | 64.09 ms |
| Seed age at copy | 831.51 ms | 805.15 ms |
| Total paced replay time | 1,556.84 ms | 1,388.26 ms |
| Consumed past observations | 68 | 8 |
| Supported history | 68 | 0 |
| Terminal worker result | READY | HISTORY rejection |
| Future proposal lead over checked source | 13,018 samples = 5.2072 ms | No proposal |

The positive proposal and all eight repeats stayed inside the unchanged
last-supported-plus-32-frame forecast horizon. The one-second seed-age bound,
two-second source deadline, 200-anchor budget and quality gates were unchanged.
The wrapper uses the existing live scanner, ordering and retention functions,
then invokes the same bounded CPU worker. It stops at a handoff proposal.

The paced producer is a separate ARM thread publishing real retained samples
into the two-second ring. It allows source time to advance during scanning,
FFTs and past-pilot processing. This tests advancing-time startup on actual
ARM hardware, but does not include concurrent FPGA DMA or physical native
admission. The earlier loaded captures separately establish continuous DMA
and rejection behavior at both native rates; those separate results must not
be presented as a completed acquired loop.

## Selection and independent review

The source is the retained `.20` recording from
`native-acquired-controller-20-v3/bootstrap-spool/capture/iq.ci16`, SHA-256
`bef04ec4eea45ac7a08048373ae1c71825f6b295ab1b7541e750811e58da91f8`.
Its complete 2.4 GB content was checked before selecting replay slices.
The positive slice begins at recording sample 170,857,894 and the control at
sample zero. Each input contains 6,250,000 samples. The replay stops once its
worker completes, without requiring the entire input to be consumed.

Before the actual ARM replay, a host diagnostic ran the same C scanner,
ordering and worker on eight historically accepted acquisitions and four
historically rejected windows. It explicitly modeled 840 ms of acquisition,
600 ms of resolution and 2.5 ms per consumed past pilot. Five of eight selected
positives reached READY; none of the four selected controls did. Three accepted
acquisitions did not establish enough later history. These are inspected
development cases, with some temporally nearby tracks; they do not estimate
independent acquisition success or calibrated specificity.

Independent review of the actual ARM outputs checked 73,326 coarse-grid values,
16 ordering scores, 34 resolver hypotheses, 76 complete integer-moment sets and
277,432 copied IQ samples against the original input slices. Integer results
and copied bytes matched exactly; FFT hypotheses matched their numerical
tolerances. The review also checked candidate selection, seed age, future
proposal lead and forecast bounds. It does not independently label the signal's
satellite identity or physical timing/frequency accuracy.

## Deployment and remaining work

The operator held the production capture lease and serial lock, attested the
radio and payload hashes, checked free memory and retained the results. Its
before/after firmware, boot identity, TX and idle-buffer receipts matched;
temporary radio files were removed. An earlier invocation was refused while
another acquisition held the shared lease and contacted no radio. Both actual
replays collected zero new RF samples and made zero native submissions.

The evidence root is
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`:

- `historical-ranked-replay-v1/`: selected host cases with modeled processing costs.
- `paced-replay-input-v1/`: exact source slices and hashes.
- `paced-replay-arm-v2-results/`: actual ARM output, journals and independent review.
- `paced_replay.c` and `qualify_paced_replay.py`: bounded replay harness and operator.

The harness uses firmware source commit `f4bd5d984`; it changes no deployed FPGA
image or production worker. Compact results and source hashes are retained in
[the evidence JSON](figures/2026_09_13_radio20_paced_arm_startup/evidence.json).

The next physical requirement remains a supported candidate reaching native
admission and sustained feedback during continuous RX, at both 30 and 60 MS/s.
Autonomous scanning/reacquisition and refinement remain unfinished. A stronger
recording demonstrates that current ARM startup can succeed; it does not remove
those hardware acceptance requirements.
