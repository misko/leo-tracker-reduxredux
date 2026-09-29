# Partial receiver timing: first completed batch

The **0.1-second regularization batch is complete**, with all eighteen
selected fits passing numerical audits. The predeclared 0.5- and 2-second
batches remain unlaunched while the receiver-cone study takes priority.
This is a published checkpoint, not completion of the three-strength study.

[Full 0.1-second report and visualization](RESULTS-s010.md) includes every
four/eight-scan result for DS7/DS8/DS9, comparison with one-timing and independent
receiver-timing baselines, held prediction, timing dispersion, initialization
diagnostics, numerical checks, and the retained failed optimizer start.

Eight-scan median errors are **2,016 m / 1,701 m / 754 m** for DS7/DS8/DS9.
DS9's late eight-scan error remains **3,798 m**. These results do not establish
reliable sub-km performance across datasets or windows. No strength has been
selected from reference errors, and no cone model is combined with this batch.

The [protocol](PROTOCOL.md) and [plan](plan.json) freeze all three strengths.
[Input hashes](input-seal.json), per-process seals under `runs/`, and the
[checkpoint hash inventory](evidence-sha256.json) bind completed evidence.
The inventory excludes itself and bytecode caches. Future strengths must add
their own results while preserving the completed s010 process evidence.

Reproduction order in a fresh output location: tests, prepare, then
`launch.py fit s010`, `launch.py held s010`, `summarize.py s010`, and
`write_batch_report.py s010`. The installed scientific interpreter specified
in launch receipts is required for fits; existing run folders are immutable.
