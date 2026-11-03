# Chronological rolling weighted-linear tracker

This is a bounded research implementation. It processes exact
receiver/channel/edge/RF lanes and source groups in chronological order. Each
hypothesis uses a weighted linear fit over at most 32 points and the selected
4, 8, or 12 second window. The default is 8 seconds. Prediction and gating use
each candidate's actual center time. CFO and alias spacing are normalized to
11.2 GHz.

The fixed physical bounds are +/-15 kHz/s rate, a 2.5 kHz residual gate plus
at most 2.5 kHz fit uncertainty (5 kHz total), a 4 second maximum gap, and
qualification at 8 sources over at least 4 seconds. A lane retains at most 24
hypotheses, including eight reserved positions for recent births. At most two
association alternatives are retained. Output is a hypothesis bank and is not
an exclusive assignment; overlapping tracks may share candidates.

Defaults were selected from the task constraints and component tests before
the frozen server and ARM observation outputs were produced. No baseline
labels were read by the tracker or used for initialization. A first bounded
run is retained under `pre-group-fix/`. Before freezing, correctness review
found two implementation defects: interleaved candidate times could split one
source group, and a hypothesis could be dropped when candidate associations
existed but every updated fit was rejected. Both were fixed and covered by
component tests. Strict contract parsing then found a serialization defect in
the alias sign and TRACK support interval endpoints; the rejected outputs are
preserved under `rejected-contract/`, and both fields now have a component
regression test. These are correctness fixes, not target-data tuning. The
final server and ARM outputs pass the shared strict evaluator.

`output/server.tsv`, `output/arm.tsv`, and `output/synthetic.tsv` are the final
host runs. Their stderr files contain machine-readable `TIMING` and `STATS`
rows; `.time.json` files record wall time and peak RSS. Synthetic evaluation
recovered both truth curves completely, with purities 1.0 and 0.9832.

Host and ASan/UBSan component tests passed. The ARM binaries were cross-built
with the same Cortex-A9 hard-float toolchain used by curvature tracks. No board
or RF work was performed. `SHA256SUMS` identifies the frozen source, binaries,
and full TSV outputs.
