# Full-8h fitted-tau and host-bracket semantics audit

This bounded, read-only audit joins only the 72 frozen Sep 21 00Z TRAIN scans
in `long_block_full_qualification/results.json` to the same 72 session IDs in
the sealed shared-epoch inference. It does not use a location, reference
coordinate, RF, validation, or test data.

The qualification metadata records 0.838--2.345 ms first-sample bracket widths
(10th/median/90th: 1.099/1.338/1.514 ms); the first scan is 1.270 ms. In the
0.2 s nuisance-scale arm, fitted absolute taus have medians 0.232 s in both
prior views, or about 177 times the matching host bracket width. The first
scan tau is about -0.629 s, about 495 times its bracket. The 1.0 and 5.0 s
arms have still larger medians (0.769 and 0.868 s). Full per-arm quantiles and
per-scan ratios are recorded in `results.json`.

This numerical difference is not evidence of a timing bug. The fitted tau is
a penalized nuisance coupled to location, fixed candidate assignments,
catalogue prediction, and per-track CFO. It is not a direct timestamp-error
measurement.

The repository's stated contract is that `begin_session` starts device
sampling before returning and that the first counter is host-bracketed
([persistent_hop.py](../../src/leo/scanner/persistent_hop.py) lines 40--47).
The authority derives UTC bounds from before/after host clocks and records
them with `receipt.terminal.first_counter` (lines 87--111). The adaptive
capture application passes the session's refined bracket and that terminal
counter into the authority
([adaptive_hop_application.py](../../src/leo/scanner/adaptive_hop_application.py)
lines 171--175 and 213--231). For host adaptive IIO, the wrapper copies an
upstream bracket and refreshes it after block zero; its source comment says
the backend can then bind the FPGA counter
([pluto_host_adaptive.py](../../src/leo/radio/pluto_host_adaptive.py) lines
371--379 and 402--431).

The installed current PPU distribution is `pluto-plus-utils` 0.1.0. Its
host-adaptive adapter has no independent bracket logic; it inherits the
persistent backend. That backend initially retains the broad metadata-OPEN
bracket, then replaces it on sequence-zero with
`first_sample_clock_bracket(evidence.block_first_counter, sample_rate_hz)`
([iio_persistent_hop.py](../../.venv/lib/python3.13/site-packages/pluto_plus/hardware/iio_persistent_hop.py)
lines 292 and 302--333). The metadata implementation takes eight
host-monotonic intervals around FPGA low-32 counter register reads after OPEN,
spaced 5 ms apart, then obtains a realtime mapping (lines 1246--1282 and
1287--1318). It extends those anchors near the sequence-zero header first
counter, fits counter to monotonic time, adds fit/realtime-map uncertainty,
and maps the resulting interval to realtime (lines 1216--1244).

Thus the current implementation is neither an IQ receive timestamp nor a
direct first-buffer-begin timestamp. It is a fitted first-counter time based
on post-OPEN, host-bracketed FPGA register reads and the first metadata-header
counter. It still does not independently establish physical register-read,
driver, or transport latency/error properties.

The qualification metadata identifies stream generation and timing algorithm,
but has no `pluto-plus-utils` version, installed-file digest, wheel binding, or
capture-time source provenance. The current installed source and hashes are
therefore recorded as a current semantic trace, not as proof of the exact
historical implementation. The historical physical mapping remains an
explicit limit.

`results.json` contains all numerical summaries, exact source line references,
and SHA-256 bindings to both input artifacts, repository sources, and the
three inspected installed PPU files. No code was changed for this audit.

`audit_numerical.py` is the lean reproducible numerical helper. It reads only
the qualification and sealed inference artifacts, writes all six per-arm
summaries and 72 per-scan absolute-tau/bracket ratios per arm, and binds both
inputs and itself by SHA-256. The checked-in `numerical_recomputed.json` was
generated with `--verify-results`; it reproduces every summary in
`results.json` before emitting the additional per-scan ratios.

```bash
.venv/bin/python reports/2026_09_23_full8h_tau_timing_semantics_audit/audit_numerical.py \
  --qualification reports/2026_09_23_long_block_full_qualification/results.json \
  --inference reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json \
  --verify-results reports/2026_09_23_full8h_tau_timing_semantics_audit/results.json \
  --output /tmp/full8h-tau-timing-numerical.json
```
