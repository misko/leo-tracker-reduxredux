# Fresh standard-server full-scan replay

This directory contains a fresh invocation of the maintained server detector on
every saved dwell in `scan-fw-f363c7f29141d0b1`. It does not reuse detector
receipts or candidate values. The public IQ store was opened read-only and no
radio was used.

The recording has 2,215 120 ms dual-receiver visits at 2.5 MS/s. Its realized
schedule covers the lower edge of channels 1 through 4; it contains no upper-edge
visit. Each receiver is analyzed with one 20 ms probe at a 120 ms stride. The
server detector retains eight candidates per receiver and applies the unchanged
0.025 fractional-margin gate.

The run passed with:

- 2,215 visits and 4,430 receiver windows;
- 35,440 retained candidates;
- 25,374 complete and 10,066 unbracketed fractional results;
- 10,066 candidates passing the fractional-margin gate;
- 2,215 unique raw-IQ hashes and 2,215 unique recording-event hashes; and
- 215.112 seconds elapsed with four host worker processes.

`qualification.json` is the machine-readable result. Its validator checks every
visit receipt against the aggregate JSONL and inventory, verifies visit/counter
ordering and 300,000-sample dwell extents, requires two receivers and ranks 0–7,
rejects nonfinite candidate numbers, and recomputes every gate decision.

The exact execution was:

```sh
sudo -n /usr/bin/setsid /usr/bin/timeout --signal=TERM --kill-after=10s 2350s \
  /usr/bin/env PYTHONPATH=/var/tmp/leo-arm-realtime-publication/src \
  /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  reports/2026_09_30_arm_full_scan_comparison/server/run_server_full_scan.py \
  --output-dir reports/2026_09_30_arm_full_scan_comparison/server \
  --workers 4 --batch-size 8 --maximum-visits 2215
```

The reference checkout was clean at
`ea2756bda8101f5a231f38e1761747766a2e0572`. The recording manifest is
`sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015`.
`summary.json` binds the maintained server source files and run configuration;
`visits.sha256` binds all per-visit receipts, and `SHA256SUMS` binds the aggregate
artifacts and validation sources.

This evidence establishes fresh saved-IQ server processing and supplies the
server side of the ARM/server/capture-time comparison. It does not establish RF
collection, upper-edge coverage, or end-to-end tracking/location parity.
