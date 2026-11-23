# Tail-energy bounds on groups of timing and carrier hypotheses

The bound rejected **zero timing groups and zero carrier rows** on the scheduled dense 20/12 ms prefix through seven eighths of the taps. That held even when the audit supplied the exact cutline and replaced every measured prefix magnitude with zero. Giving away the final eighth of every broad stage across dense DS30-0008 would save about **0.81 CPU s** at the audited rates, versus **3.49 s** needed under the first-four zero-wait model. The partial-dot bound stops here. [Acquisition budget](warm-recording-budget.md)

This audit tests the broad quarter-rate search in experiment 3. The earlier 1.19 CPU-second estimate covered seven of 14 frames in the **subsequent** four-candidate native refinement bank. Here the receiver first ranks 3,333 timing phases with eight lag correlations, then scores 12 surviving timing rows on the signed carrier grid, and only then sends four nominations to refinement. The 12 ms primary and 20 ms anchor use the same timing and carrier grids and differ in how many waveform frames contribute to the modes. The actual 20 ms signed-residual pass has fresh modes and an independent cutline. [Proposed experiment](next-2x-after-rank-census.md) · [Earlier refinement bound](refine-bound.md) · [Mixed schedule and whole dense clocks](dense-full-short-raw.md)

## Optimistic rejection test

For a template \(h\) and received slice \(x\), split the dot product after \(k\) taps. In exact arithmetic its magnitude is at most

\[
  |\langle x_{<k},h_{<k}\rangle|+\sqrt{E_{x,\ge k} E_{h,\ge k}}.
\]

The timing score sums the squared per-lag bounds with the original normalization by the received window energy and unit-energy lag template. A timing group can be rejected only when the bound for every row in the group is strictly below the last of the 12 selected timing scores. The oracle supplies that score and grants free search order and circular exclusions. For carrier, combine the two modes in a norm and use the sum of their received energies as the original denominator. Modulation across signed CFO keeps template energy constant, so the tail term can be shared by the whole carrier row. The oracle supplies the fourth best eligible seed score after the original within-row circular separation. An equal or nonfinite score keeps the entire group. Because the bound is strict, skipping a certified loser would preserve frozen tie order and the nomination that can trigger signed cancellation.

The instrumentation leaves both original FFT paths intact. It records their exact cutlines and the original modes and pilot samples. It gives the partial dots a magnitude of zero and costs nothing for forming them, prefix sums, bound comparisons, rounding allowances or oracle cutlines. A practical triangle/Cauchy bound adds a nonnegative prefix magnitude and would reject at or after this optimistic trial. At each eighth of the aperture, the audit counts whole contiguous 32-phase timing groups and whole carrier rows with all scores below the cutline. Individual timing phases supply an additional optimistic comparison. It also credits each rejected group with avoiding a fraction of the complete stage clock, proportional to remaining taps and group size. The released stage uses shared FFTs, so these modeled savings are more generous than discarding groups after a shared transform. The prototype does not claim a floating-point certificate or apply a pruning decision to exported factors.

Stage clocks surround only timing and carrier search in the instrumented timing objects. Both release controls relink byte for byte. Trace objects compile with the original optimization and floating-point flags without PGO, so archived PGO scopes separately anchor the timing scale. The context, signed confirmation, cancellation, and original-sample fractional verification stay on their original paths in both builds. Source and both build manifest hashes are checked before any native call. [Instrumentation and count calculations](whole_group_receiver_bound.py) · [Original PGO stage profile](receiver-polyphase-timing.md)

## Saved weak and dense results

The audit uses the 18 previously nominated weak DS26 stereo clips and 24 scheduled DS30-0008 stereo visits from an existing authenticated private copy. Each aperture was exercised on both antennas at every visit to measure it separately. The dense schedule itself issued 16 full and 32 short lane calls. The trace matched the released factors byte for byte across all 168 aperture-specific calls, including 43 residual factors, and reproduced each recorded continuation state. Neither aperture's short chronology yielded a continued selection. The per-aperture parity also preserves the inputs to continuation on the mixed schedule.

| Slice and scan | Scouts | Timing groups prunable at 7/8 taps | Carrier rows prunable through 6/8 taps | Carrier rows prunable at 7/8 taps |
|---|---:|---:|---:|---:|
| Dense, released schedule only | 57 | 0 | 0 | 0 / 684 |
| Dense, hypothetical all-short primary | 48 | 0 | 0 | 0 / 576 |
| Dense, hypothetical all-full primary | 48 | 0 | 0 | 1 / 576 |
| Dense, hypothetical all-full residual | 33 | 0 | 0 | 0 / 396 |
| Weak, hypothetical all-short primary | 36 | 0 | 0 | 12 / 432 |
| Weak, hypothetical all-full primary | 36 | 0 | 0 | 24 / 432 |
| Weak, hypothetical all-full residual | 36 | 0 | 0 | 1 / 432 |

No individual timing phase qualified on any of the 237 scouts, even before requiring all phases in a group. The only dense carrier-row opportunity came from a full primary on a lane assigned to the 12 ms path. At the dense per-aperture trace clocks and full recording call counts, the measured opportunities project approximately **0.00010 CPU s** of savings. The scheduled subset had zero. A conservative Float32 implementation must retain marginal or ambiguous rows and compute any unresolved ranks with the original arithmetic. That would add work and can further lower these counts. No modified ranking, position solve or broader transfer test ran. [Sealed native receipt](measurements/whole-group-receiver-bound.json.gz)

## Cost of the check

The trace's dense per-aperture clocks project **5.21 CPU s** across 11,834 short calls and **1.26 CPU s** across 1,696 full calls, including the reached residual carrier and timing stages. Those estimates use the slower instrumented carrier stage, approximately 263–267 µs per scout, compared with the archived 142 µs PGO carrier clock. Timing used about 168–179 µs per scout. The 7/8-tail test keeps all earlier work at those clock rates. Even the deliberately excessive grant of one eighth of the dense recording's entire **17.351 s** native clock would be **2.17 s**, with untouched stages such as FIR, signed cancellation, refinement, and verification included in that grant. These are time-attribution models under proportional work assumptions. The measured search uses shared transforms, so an output group discarded after those transforms cannot recover their arithmetic. [Dense native CPU](dense-full-short-raw.md) · [Archived PGO clocks](receiver-polyphase-timing.md)

In a direct time-domain implementation, just reaching 7/8 taps over all timing cells would perform about **32.29 million** complex products per scout. Applying the same split to both modes across all eligible carrier bins adds **38.75 million**. The pure product count alone would take about 2.96 ms per scout even at four complex products per cycle and 6 GHz, before summing the dots, building the bounds or running the untouched receiver. A factorized implementation can avoid those direct product counts. A bound applied to shared FFT outputs needs to skip a separable operation. The earlier short carrier FFT did that and still projected only 3.2–5.7% of the carrier stage with perfect reuse. The negative result covers the contiguous-prefix triangle/Cauchy test. Different template partitions or a different enclosure would need an independent budget and evidence. [Short carrier FFT bound](carrier-fft-bound.md)

## Reproduce

Run with the existing private DS30-0008 segment and original weak archive. All generated files stay on tmpfs. Three component tests passed covering ties, nonfinite scores, a terminal partial group, both receive modes, wrap endpoints, and the per-lag normalization. The first command attempt stopped before compiling because the short receipt pin had been transcribed incorrectly. The single completed native audit verified both released libraries and the source and recording pins before scoring either slice.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
main_tree=/home/mouse9911/gits/leo-tracker-reduxredux
private=/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt
dense="$private/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"
work=$(mktemp -d /dev/shm/leo-v3-whole-group.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" timeout 50s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.whole_group_receiver_bound "$work/native" "$release/assets" \
  "$main_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" "$dense" \
  > "$work/receipt.json"
```

The uncompressed receipt SHA-256 is `e9a965910ca79b8614fcbf72ea21ced62aba32100aa1ee5dc24361bb660d2594`. It includes both original and trace binary digests, I/Q digests, installed versus trace complete call CPU, and counts and stage clocks for each scan.
