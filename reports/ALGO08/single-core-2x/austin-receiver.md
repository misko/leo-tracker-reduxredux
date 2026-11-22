# Two-scan acquisition on the Austin field excerpt

The archived UT Austin single-antenna excerpt supplies 50 ms of measured broadband I/Q and author-provided relative frame times. The previous wide GLRT study authenticated and transformed this excerpt and tested the original Qin waveform. This use of the known excerpt is an independent physical site check at the receiver boundary. The position solver needs a longer timed recording on multiple channels. [Previous receiver and field inventory](../regional-release/README.md#independent-physical-stations)

Use the two disjoint 20 ms periods starting at 0 and 20 ms. Use both previously defined receiver tuning edges on each period. The two frequency edges of one period share the same antenna and capture time. Also replay the existing deterministic phase-randomized null for each period and edge. Check every input digest against the archived wide-GLRT study. Evaluate the deployed detector and the original and integer-FIR research receivers. For both research receivers evaluate the full and primary-only entries. Supply only the measured antenna in lane zero, with zero padding in the unused lane of the stereo ABI. Each call uses the ordinary full search band with no time hint. Compare native ordered exports and score the strongest verified factor against the first complete author-marked frame of each physical window modulo the known frame period, with the existing ten-sample tolerance. Treat an empty export as a miss. The null has no true phase. Report measured carrier offsets separately from relative-frame agreement.

## Results

Deployed ALGO08v2, the floating research filter and the integer filter found the published frame phase on **all four edge/window combinations**. The largest absolute timing discrepancy was **0.645 sample**, about **65 ns** at 10 MS/s. Each full detector exported two factors per physical input. All ordered factor bytes, including scores and frequencies, matched across the three full detectors. The floating and integer primary-only entries exported one identical factor per physical input. All five entries exported zero factors on all four nulls. [Per-input results and hashes](measurements/austin-integer-receiver.json)

| Edge | Window start | Integer filter phase error (samples) | Measured signed CFO (kHz) |
|---|---:|---:|---:|
| Lower | 0 ms | +0.645 | −194.934 |
| Lower | 20 ms | +0.031 | −194.946 |
| Upper | 0 ms | +0.595 | −141.465 |
| Upper | 20 ms | +0.002 | −141.493 |

The authors' timing marks supply an external reference for the strongest factor. This check has no independent absolute carrier-frequency or second-satellite label. The result extends physical evidence for waveform acquisition to a second location. All physical end-to-end position results still come from Gauss. [Integer receiver timings](receiver-integer-fir.md) · [Replay code](austin_receiver_trial.py)

## Reproduction on Gauss

The earlier field study stores its authenticated archive in the local cache and its reference receipts in the original workspace. The detector calls use the same pilot assets as ALGO08v2. One low-priority job reads this 50 ms excerpt.

~~~bash
rel=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist=/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_19_receiver_screening
p=/tmp/leo-algo08v2-2x-bench
t=reports/ALGO08/single-core-2x
flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$t" \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python "$t/austin_receiver_trial.py" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip "$hist/physical/raw-source-audit.json" \
  "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz" "$rel/assets" \
  "$p/receiver-residual-integer-control.so" "$p/receiver-residual-integer.so"
~~~
