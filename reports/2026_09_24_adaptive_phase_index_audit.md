# Adaptive scan phase/index audit

This is a read-only replay of the deployed relative-phase analysis for
`scan-fw-1aa1d50103d97388`. It does not modify the capture, the production
release, or any published result. The frozen result has 64 selected visit
artifacts, 26 supported visits, and 26 visits with broadband resultant
`R >= 0.8`.

## Index and channel trace

The capture source contains 2,215 visits. For every one, the source ordinal
equals `event.visit_index`; all 64 frozen analysis rows therefore read the
intended IQ dwell. Each dwell has 300,000 samples (`120 ms` at `2.5 MS/s`) and
two complex columns. The source converts compact CI16 as `[:, receiver, I/Q]`,
so column 0 is RX0 and column 1 is RX1. The replayed rows reproduce the frozen
metadata exactly: visits 569 and 590 are channel 3 / upper edge; 1677 is
channel 2 / upper; and 324 is channel 1 / upper.

The adaptive visit contract independently constrains `channel = target_index %
4 + 1` and `edge = upper` for target indices 4--7. Thus there is no visit-to-IQ
ordinal, channel, or edge mismatch in this scan.

## What R measures here

The reported `band_phase_resultant` is not the raw FFT-bin coherence. The
first half of a dwell fits a physical-overlap transfer response. In the held
second half, the even 64-bin groups estimate a common phase and the odd groups
measure a residual phase. `R = |mean(exp(j * residual_phase))|` is the
concentration across those held B-band blocks. The 4096-point FFT spacing is
610.3515625 Hz. Pilot-frame R is a separate local measurement built from
shared frame starts and symbols 2 through 65, with template-energy centroid
timestamps; it is not the broadband R screen.

## Raw-IQ perturbation replay

Two high-R and two low-R visits were replayed from their original IQ with one
change at a time. The full machine-readable rows are in
`raw-perturbation-results.json` and `raw-perturbation-R.csv`.

| Visit | Frozen broadband R | Best low-R response-bin wiggle | CFO -1 / +1 FFT bin | Consistent RX swap |
| ---: | ---: | ---: | ---: | ---: |
| 569 | 0.955 | n/a | 0.489 / 0.562 | 0.946 |
| 590 | 0.935 | n/a | 0.681 / 0.170 | 0.894 |
| 1677 | 0.275 | 0.403 | unavailable / 0.055 | unavailable (no A-band response) |
| 324 | 0.245 | 0.393 | unavailable / 0.075 | 0.129 |

Moving the initial frequency-response lookup by one or two FFT bins barely
changes a strong dwell (at most 0.0013 in these two checks). It never rescues a
low dwell: the best tested values are 0.403 and 0.393, both far below 0.8.
Applying a one-bin CFO error sharply reduces the high values, while reversing
the CFO sign either produces no physical support or R near 0.05. This is the
expected sensitivity to carrier registration, not the pattern of a common
integer-bin error. A fixed bin offset would instead improve both low dwells in
the same direction and not destroy both strong dwells.

For the first paired pilot probe in each dwell, frame-lattice offsets of +/-1
and +/-2 samples, symbol-grid shifts of +1/+2, independent offset-authority
shifts of +/-610 Hz, an RX-column swap with correspondingly reversed seeds,
and the opposite pilot edge were tested. No perturbation consistently improves
either high or low case. The matched RX swap preserves pilot R within 0.0005
for every replayed dwell and reverses the fitted frequency sign, as required
by RX1-times-conjugate-RX0. The negative symbol shifts are deliberately
invalid because the shifted first symbol has zero template energy; this is an
explicit template-boundary guard, not silent wraparound.

The first-probe pilot R values are only 0.54--0.65 in these examples, including
the broadband high-R dwells. An occasional wrong-edge or timing wiggle returns
a similar value because this local probe is weak; it does not create a
broadband high-R result. The broadband held-out screen and local pilot probe
should therefore not be conflated.

## Conclusion

No tested +/−1 or +/−2 FFT-bin, response-bin, sample/frame index, pilot-symbol
index, edge, carrier-sign, or consistently swapped-receiver change rescues the
low-R dwells. Visit/IQ indexing and channel/edge mapping are also exact. The
evidence favors genuine dwell-to-dwell variation in the held broadband
coherence/support over an off-by-one implementation error. This does not make
the high-R values a geometric or source-identity claim; it only rules out the
examined indexing and carrier-registration explanations.

## Reproduction

The raw replay needs the deployed release and read-only adaptive corpus:

```bash
sudo -n /opt/leo-tracker/releases/c5f03f4bb0e803b7b58d8b2925c1e88e7d683954/.venv/bin/python \
  reports/figures/2026_09_24_adaptive_phase_index_audit/audit_replay.py \
  > reports/figures/2026_09_24_adaptive_phase_index_audit/raw-perturbation-results.json
.venv/bin/python reports/figures/2026_09_24_adaptive_phase_index_audit/summarize.py
```

The mapping audit is recorded in
`figures/2026_09_24_adaptive_phase_index_audit/visit-channel-iq-mapping.json`.
