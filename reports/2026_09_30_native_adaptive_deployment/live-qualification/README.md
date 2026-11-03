# Live scanner qualification telemetry

This directory preserves every live run, including the initial failed v1
runs. `summarize.py` parses scanner event and summary schemas v1 and v2 using
strict JSON: duplicate keys, non-finite JSON literals, unknown telemetry
schemas, missing fields, extra fields, malformed JSONL, and receipt/log
accounting differences fail the command.

A receipt may explicitly record a `pre_execution_rejection` when an archived,
hashed proof shows that the wrapper rejected the command before it forked the
scanner. The summarizer verifies the proof file and hash, requires empty
scanner output and a nonzero exit, and reports scanner, detector, cadence, and
cleanup metrics as unavailable. It does not turn the empty output into zero
visits or a successful qualification run.

Regenerate the report after a run receipt arrives:

```sh
.venv/bin/python \
  reports/2026_09_30_native_adaptive_deployment/live-qualification/summarize.py
```

The command rewrites `summary.json`. It reports intact and incomplete visits,
dwell and feedback-state inventories, device-counter cadence and same-target
revisit distributions at 2.5 MS/s, detector queue/runtime distributions when
v2 provides them, drops, missing samples, stop and cleanup statuses, and the
whole-process CPU/RSS receipt. Percentiles use nearest rank, `ceil(p*n)`, and
carry that method in every distribution.

Monitor samples have an explicit layout: `/proc/uptime`, XADC raw, offset,
scale, `/proc/meminfo`, then scanner `/proc/PID/status` and `/proc/PID/stat`.
Temperature is `(raw + offset) * scale / 1000` degrees Celsius. The summary
also retains monitored RSS/high-water memory and the before/after radio state.
An absent monitor or XADC sample remains explicitly unavailable.

Candidate counts are operational telemetry only. These live runs contain no
recovery denominator, labelled candidate truth, or server-equivalent ground
truth. Quiet runs with zero candidates neither prove failure nor scientific
specificity, and nonzero counts do not qualify recovery or detector parity.

`run_live.py` is an adapted, self-contained reproduction harness based on the
temporary script used for the measurements; it is not a byte-exact archive of
that script and is not production software. It contains no secret value, requires an
explicit `--authorized` flag, reads the password through the configured
credential-file path, pins SSH host verification, enforces the persisted
aggregate budget, transfers no raw IQ, and refuses duplicate or concurrent
ledger entries. Finished runs use a reduced charge only when the original
reservation remains in the ledger and an archived receipt hash proves the
host elapsed upper bound, `ceil(elapsed)` charge, finished status, and zero
cleanup statuses. Active runs and finished runs without complete proof retain
their full reservation. Do not invoke it without current live-RF authorization.
