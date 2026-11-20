# Portable v5 with broad held Doppler support

The held-arc gate requires at least two validated arcs for each unresolved arc, in addition to the original minimum spread across satellites, frequency channels and capture time. The denominator comes from held-eligible native time–frequency arcs, including those without a matching orbit. The gate groups substantially overlapping same-frequency receiver tracks so that observing one arc twice does not enlarge that denominator. It trains the same orbital shape on disjoint clock blocks and uses the same bounded five-refresh receiver after admission. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

It genuinely withheld both historical omitted offers while returning both containing fixes on the same original native packets. The independent containing offer also returned, and the shuffled control withheld. The independent omitted offer passed exactly at the eight-of-twelve arc threshold and falsely published in both arms. No coverage worker reached the deadline. [Prediction lock](prediction-lock.json) · [Scores](scores.json)

| Query | Validated held arcs | Status and wall time | Published error in km, zero / fitted | Conditional Doppler RMS in Hz, zero / fitted |
|---|---:|---|---:|---:|
| Historical Site 1, containing | 12/12 | Returned, 65.9 s | 0.527 / 0.483 | 23.746 / 23.744 |
| Historical Site 1, omitted | 6/12 | Withheld, 17.7 s | — | — |
| Historical Site 2, containing | 11/12 | Returned, 105.7 s | 0.728 / 0.594 | 24.045 / 24.051 |
| Historical Site 2, omitted | 7/12 | Withheld, 19.4 s | — | — |
| Fresh site, containing | 12/12 | Returned, 65.2 s | 0.496 / 0.679 | 23.831 / 23.828 |
| Fresh site, omitted | 8/12 | False publication, 145.0 s | 72.664 / 66.148 | 23.514 / 23.551 |
| Fresh shuffle | — | Withheld, 21.9 s | — | — |

The training optimum on the fresh wrong offer touched the tile edge. Its conditional RF RMS was lower than the fresh containing solution's. Fitted RF calibration reduced the fresh containing RF RMS by 0.0031 Hz while increasing its position error by 182 m. The historical containing rows and their original stock comparisons are development evidence. There is one independent site, and neither calibration arm qualified for reliable omitted-region rejection. [Historical rows](historical.jsonl.gz) · [Fresh rows](fresh.jsonl.gz)

To repeat this experiment in a new report directory, add `--seed-hex` from the published `labels.json` to reproduce the fresh capture and offers. The fixture generator makes a second unused site internally. Only rows in the frozen predictions entered the experiment or the scores.

```sh
mkdir -p /tmp/portable-gate-coverage-report
.venv/bin/python -m tools.pipeline_eval.qualification.portable_gate_coverage_trials \
  --scratch /tmp/portable-gate-coverage --report /tmp/portable-gate-coverage-report --cpus 4 5
.venv/bin/python -m tools.pipeline_eval.qualification.portable_gate_coverage_trials \
  --score --scratch /tmp/portable-gate-coverage --report /tmp/portable-gate-coverage-report
```
