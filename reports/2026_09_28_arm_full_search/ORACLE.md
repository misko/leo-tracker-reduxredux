# ARM full-search native-port oracle

`export_oracle.py` makes a four-probe debugging fixture from saved DS7 IQ: the
first 2.5 MS/s input in `inputs.json` order for lower and upper edges, receiver
0 and receiver 1, and probe 0 only. Selection is made from input metadata before
any detector result is read.

Pass `--all-rates` for a bounded 16-probe portability fixture: the first lower
and upper saved window at each of 2.5, 5, 7.5, and 10 MS/s, still receiver 0
and receiver 1 at probe 0 only. The default remains the original four probes.

Each case has little-endian C-order binary sidecars: a complex128 raw probe
(`real,imag` interleaved), complex128 exact and rolled-control templates, and a
float64 coarse grid. The coarse grid is CFO-major with 11 rows for -400 through
+400 kHz in 80 kHz steps and `round(rate/750)` epoch columns. `oracle.json`
records every retained original acquisition candidate, including duplicates,
then the original baseline pilot module's conditioned 512-bin GLRT result.
The 512-bin size is intentional: it is not the scanner's newer 64-bin path.

The exporter loads the SHA-recorded pre-optimization acquisition and pilot
source files. It uses the scanner's acquisition settings (20 ms, eight retained
candidates, 5 sample / 10 kHz candidate separation) but never invokes the full
11-probe dwell decision. It compares the exported acquisition epoch/CFO and
final GLRT fields with the matching sealed `baseline-01` original repeat-0
probe, rejecting any mismatch above `1e-10` in floating fields.

Run it with:

```bash
PYTHONPATH=src python3 reports/2026_09_28_arm_full_search/export_oracle.py \
  --inputs /var/tmp/leo-ds7-large-arm-20260928 \
  --output /var/tmp/leo-arm-full-search-oracle
```

The output is a debugging fixture for a cross-language port. It is not a new
scientific run and does not select a positive outcome.

`compare.py` invokes the native binary once for each of the four sidecars and
writes each stdout/stderr response to `results.jsonl` before recording any
comparison failure. Grid byte equality and field equality are reported apart
from tolerance-based parity. The tolerance thresholds are 2e-11 for coarse-grid
scores, 2e-9 for detector scores, and 2e-6 Hz for CFO values; they allow normal
double-precision reduction and peak-interpolation order differences while being
far below a score gate or a sample/CFO hit criterion. Hit metrics are a separate
one-to-one matching result using two samples and 8 kHz, and never turn an
ordered-parity failure into a pass.
