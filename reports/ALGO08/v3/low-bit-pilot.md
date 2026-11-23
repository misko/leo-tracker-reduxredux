# Direct low-bit pilot search exceeds the acquisition budget

Even an optimistic one-bit direct bank needs **6.42 ms per lane** for 14 frames on a deliberately coarse timing and signed-CFO grid. The complete receiver callback budget is **0.581 ms per lane** in the measured cold CPU comparison and **0.689 ms** in the projected warm elapsed comparison. The direct bank fails before original-sample confirmation, pilot cancellation, proposal ranking, or continuation. The trial stopped at operation counts and synthetic representation checks. [Prespecified scope](low-bit-pilot-protocol.md) · [Receipt](measurements/low-bit-pilot.json)

The earlier Q15 FIR reused a signed 16-bit VNNI dot product but changed just the decimator. It cut that stage by 37.8% and the complete native call by 2.7–3.8%. The earlier linear pilot projection scored every timing cell on a coarse signed band using two frames and four symbols. It retained seven of 91 verified factors. Extending the aperture independently in the differential experiment still lost 25 of 112 factors. Those results motivate charging the independent frame groups, a broad signed search and the actual residual. [Integer FIR and published behavior](../single-core-2x/receiver-integer-fir.md) · [Linear projection](../single-core-2x/receiver-projection.md) · [Full-aperture differential scout](differential-fold.md)

## Work on the whole callback boundary

The warm calculation uses the measured 37.338 s callback CPU as an estimate for the historical 52.70 s warm acquisition elapsed, leaving 15.36 s outside the callback. With half the original solver time and the original publication tail, the warm acquisition allowance is 24.68 s. That leaves 9.32 s for a complete replacement callback over 13,530 lanes. The cold acquisition CPU calculation grants zero publication cost and halves the measured 58.96 s CPU. Keeping the measured 21.62 s outside the callback leaves 7.86 s. The separately measured cold outside-callback elapsed was 61.96 s, larger than half of the 99.53 s acquisition elapsed even before the receiver runs. [Measured split and cache](https://github.com/misko/leo-tracker-reduxredux/blob/7146070824b07bc3589e99d1318171fcfa3afc2e/reports/ALGO08/v3/acquisition-split.md) · [Warm archived clocks](first-55/stage-clocks.csv)

| Grid and independent frames | Timing × signed CFO cells | One-bit hypothetical popcount | Two-bit hypothetical popcount | Byte-expanded VNNI |
|---|---:|---:|---:|---:|
| Quarter-rate grid, 14 frames | 3,333 × 2,621 | 94.27 ms/lane | 377.10 ms/lane | 691.34 ms/lane |
| Coarse grid, 14 frames | 1,667 × 357 | 6.42 ms/lane | 25.69 ms/lane | 47.10 ms/lane |
| Coarse grid, one free folded frame | 1,667 × 357 | 0.459 ms/lane | 1.835 ms/lane | 3.364 ms/lane |

The count grants 704 quarter-rate complex taps per frame, the measured 148 raw and residual scouts per 96 dense lanes, a 6 GHz clock, and a sustained four useful 256-bit operations per cycle. A complex one-bit dot directly combines four real sign dot products. Each sign dot uses length minus twice the XOR popcount. Two bits per component give four products of sign planes per real dot. Byte-expanded VNNI processes sixteen complex taps per 256-bit dot for each of the real and imaginary outputs. The hypothetical 256-bit popcount is itself unavailable as a native Gauss instruction. XOR, accumulation, packing, layout, normalization, and ranking are all free in the table. Granting an even stronger hypothetical operation that supplies both complex outputs per packet in one instruction would still leave **1.61 ms/lane** for the coarse full-aperture direct search. [Counting code](low_bit_pilot_screen.py)

The coarse grid grants 8-native-sample timing spacing and up to about 4.5 kHz CFO spacing. It does not establish the coverage of the narrower original search. At 704 quarter-rate taps, a uniform coherent aperture at the midpoint of a 4.5 kHz carrier interval retains about 21% of ideal coherent power. Actual coded weights and frame timing change that response. The single folded frame further grants perfect coherent alignment and interference handling without charging their estimation.

A 50,000-sample quarter-rate lane uses 12.5 kB or 25 kB for one or two bits per component. At native rate the same packed lane takes 50 kB or 100 kB, down from 800 kB of signed I/Q on that antenna. The underlying 1.6 MB stereo raw window still goes through the installed authenticated reader. Even at quarter rate the fine grid's templates occupy 461 kB or 923 kB per pilot edge if stored at every carrier cell. A materialized Float32 score grid writes 34.94 MB per fine sweep or 2.38 MB per coarse sweep, which are 53.87 MB and 3.67 MB per lane at the dense mix. The model permits streaming maxima with zero grid writes and credits no bandwidth penalty in its rejection calculation.

## Weak companion information

The synthetic screen uses both digest-pinned production pilot edges, both signed CFO orientations, independently shifted weak companions and the matching rolled controls. It generates full 20 ms windows with shared noise in each pair. The raw pair compares signed-I/Q samples with and without the weak companion. Its separate residual pair grants exact removal of the primary before fresh signed rounding and packing. This is a representation measurement. It supplies no timing or CFO to a receiver and makes no pilot detection decision.

| Exact weak companion RMS relative to primary | Raw signs changed | Raw two-bit levels changed | Ideal residual signs changed | Ideal residual two-bit levels changed |
|---|---:|---:|---:|---:|
| 0.05 | 1.52–1.53% | 3.31–3.41% | 6.94–7.05% | 15.55–15.73% |
| 0.10 | 3.01–3.04% | 6.71–6.74% | 13.34–13.62% | 30.44–30.68% |
| 0.20 | 5.84–5.94% | 13.19–13.33% | 23.40–23.45% | 50.39–50.63% |
| 0.40 | 11.13–11.61% | 25.79–26.24% | 33.73–33.95% | 65.54–65.87% |

At the weakest setting, **98.39–98.43%** of the original signed ADC components differ between paired exact-pilot inputs. Raw sign and two-bit change vectors have squared projection onto the original quarter-rate change of **0.023–0.024** and **0.051–0.054** respectively. Granting ideal signed cancellation first raises those projections to **0.106–0.109** and **0.242–0.246**. The rolled controls give comparable category change fractions and projection ranges. These measures characterize the available change signal and do not separate a pilot from a rolled control. The constructed cell-interior examples have nonzero waveform additions and identical entire packed arrays for either quantizer, including when their separate RMS values set the thresholds. An original-sample check can distinguish input differences that are unavailable to the packed bank. [Both-edge synthetic values and collision witnesses](measurements/low-bit-pilot.json)

For comparison, a unit Gaussian calculation at weak correlation gives one-side efficiencies of 0.637 and 0.881. Quantizing both sides gives 0.405 and 0.776, equivalent to about 3.92 and 1.10 dB loss under that model. The two-bit levels are ±1 and ±3 with a threshold of one standard deviation. The calculation follows from \(E[XQ(X)]^2/E[Q(X)^2]\), applied once per quantized side. It excludes the deterministic stronger pilot, signed rounding, and normalization in measured I/Q.

## What remains after search

The separate directed-receiver experiment retained all measured dense factors with the original exact check and exact pre-verifier timing and CFO. Even with proposal search and empty-lane checks free, it cost **0.846 ms per dense lane**. The more permissive guarded fixed check with oracle final fractional timing, free perfect routing, and no false slots cost **0.368 ms per lane**. Adding even that guarded check to the one-bit free-folded coarse search gives **0.827 ms per lane**. Two planned proposal slots with actual negative checks and oracle times cost 0.536 ms per lane for the guarded directed path alone. An empty dense lane cost 0.098, 0.158 or 0.270 ms for one, two or four decoy checks. Those old measurements already include the independent original-sample gates and reached signed residual work. They give no measured cheap substitute that retains weak residuals and exact scores. [Directed verifier and negative-lane measurements](directed-verifier.md)

The direct packed bank misses the budget even with free confirmation. No receiver or saved raw-prefix replay was needed to reach that stop decision. A substantially shared transform or independent coded acquisition statistic would be a different mechanism with its own timing and weak-carrier qualification. No calibrated position or cross-site transfer was measured here.

## Reproduce

```sh
tree=/home/mouse9911/gits/leo-tracker-reduxredux
bench=/tmp/leo-algo08v2-2x-bench
split=$(mktemp /var/tmp/leo-v3-low-bit-split.XXXXXX)
git show 7146070824b07bc3589e99d1318171fcfa3afc2e:reports/ALGO08/v3/measurements/acquisition-split-DS30-0008.json > "$split"
lock() {
  flock -x "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 timeout 22s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD:$PWD/src" "$tree/.venv/bin/python" -BPs "$@"
}
lock -m reports.ALGO08.v3.low_bit_pilot_screen "$split" \
  reports/ALGO08/v3/first-55/stage-clocks.csv /opt/leo-algo08/current/assets \
  reports/ALGO08/v3/measurements/directed-verifier.json.gz
lock -m pytest -q tests/pipeline_eval/test_low_bit_pilot_screen.py
```

Four component tests passed, covering packed work counts, callback arithmetic, indistinguishable quantized inputs and Gaussian efficiency.
