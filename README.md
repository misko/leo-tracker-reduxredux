# LEO Tracker

LEO Tracker is a contract-first acquisition, processing, and observation system
for one or two Ethernet-connected Pluto+ radios with up to two receive channels
per radio.

The repository is intentionally a fresh implementation. The historical
`leo-tracker` and `leo-tracker-redux` repositories are scientific references and
regression oracles, not runtime dependencies.

The authoritative architecture, delivery order, and acceptance gates are in
[`plan.md`](plan.md). Until every gate there is satisfied, work should advance
the earliest incomplete dependency rather than adding parallel architecture.

Core operating rules:

- compressed raw IQ and analysis artifacts live beneath `/srv/bulk/leo`;
- PostgreSQL stores lifecycle state, jobs, lineage, and searchable summaries;
- raw recordings and published analysis runs are immutable;
- reprocessing atomically promotes a replacement run only after it succeeds;
- the LAN web UI is read-only;
- acquisition and processing controls are local CLI operations;
- QNAP is an explicitly read-only import source;
- TEST recordings use the production ingest path and are retention-protected.

How a committed recording is actually analyzed — the ten-stage receiver-path
DAG, the probe geometry, the GLRT detector bank, and the trajectory-feedback
replay — is documented in the
[Standard-v2 analysis path](docs/analysis/standard-v2-analysis-path.md). All of
its evidence is candidate-only.
The additive, non-authoritative Hough comparison product is documented in the
[alternate CFO line product](docs/analysis/alternate-cfo-line-product.md).
The production acquisition budgets, deterministic 1-in-8 dwell routing, and
promotion boundary between lanes are documented in
[Standard and Research analysis pipelines](docs/analysis/standard-vs-research-pipelines.md).

Production setup and recovery are documented in the
[`operator runbook`](docs/operations/runbook.md). Installable systemd templates
and the non-secret environment example live under [`deploy/`](deploy/). The
deployment defaults keep unattended retention disabled until an operator has
reviewed a dry run and creates the explicit enable marker.

The [acquisition soak guide](docs/operations/acquisition-soak.md) documents the
resumable 24-hour evidence layout and its versioned acceptance policy. A short
harness run is not the production 24-hour gate.
