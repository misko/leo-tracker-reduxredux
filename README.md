# LEO Tracker

LEO Tracker is a contract-first acquisition, processing, and observation system
for one or two Ethernet-connected Pluto+ radios with up to two receive channels
per radio.

The repository is intentionally a fresh implementation. The historical
`leo-tracker` and `leo-tracker-redux` repositories are scientific references and
regression oracles, not runtime dependencies.

The stable documentation entrance is [`docs/README.md`](docs/README.md). It
links the current scientific understanding, architecture, Standard and Research
pipelines, evidence ledger, operations, qualification, and documentation
standard. [`plan.md`](plan.md) remains the delivery record and acceptance plan;
current runtime behavior is defined by code, contracts, tests, and the
canonical pages under `docs/`.

Core operating rules:

- compressed raw IQ and analysis artifacts live beneath `/srv/bulk/leo`;
- PostgreSQL stores lifecycle state, jobs, lineage, and searchable summaries;
- raw recordings and published analysis runs are immutable;
- reprocessing atomically promotes a replacement run only after it succeeds;
- the LAN web UI serves immutable scientific products and, when explicitly
  configured, can queue acquisition and independent Standard/Research runs;
- retention, hardware recovery, and release cutover remain audited operator
  workflows;
- QNAP is an explicitly read-only import source;
- TEST recordings use the production ingest path and are retention-protected.

The current understanding of the transmitted waveform, known pilot, QAM, CFO
aliases, local modulo-π phase, and claim boundary is documented in
[Starlink transmissions](docs/concepts/starlink-transmissions.md). How a
committed recording is processed by the current 12-job fused graph is
documented in the [Standard analysis
pipeline](docs/pipelines/standard-analysis.md). All signal evidence remains
candidate-only.
The additive, non-authoritative Hough comparison product is documented in the
[alternate CFO line product](docs/analysis/alternate-cfo-line-product.md).
The denser profile, deterministic 1-in-8 dwell routing, offline experiment
method, and promotion boundary are documented in the [Research analysis
pipeline](docs/pipelines/research-analysis.md). The [evidence
ledger](docs/research/evidence-ledger.md) maps the complete versioned report
set to current conclusions and caveats.

Production setup and recovery are documented in the
[`operator runbook`](docs/operations/runbook.md). Installable systemd templates
and the non-secret environment example live under [`deploy/`](deploy/). The
deployment defaults keep unattended retention disabled until an operator has
reviewed a dry run and creates the explicit enable marker.

The [acquisition soak guide](docs/operations/acquisition-soak.md) documents the
resumable 24-hour evidence layout and its versioned acceptance policy. A short
harness run is not the production 24-hour gate.
