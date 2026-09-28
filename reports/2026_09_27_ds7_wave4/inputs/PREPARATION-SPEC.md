# Wave4 chronological group8-02 preparation

This frozen preparation selects chronological plan captures 009–016 before any
prediction or score is inspected. It uses unchanged `tools/ds7_combined_export.py`,
which invokes the original exporter and bank policy without scientific parameter
changes. The wave3 closeout hashes match the current combined exporter
`6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729` and
baseline exporter `4d2e4bb96e687ca9fe1a035c138c87e55d2976d0136bffac182b1bc380c42dc4`.

Cached source reads are serialized. Each privileged process is controlled by a
root-side 180-second timeout; the batch controller is capped at 1,200 seconds.
It uses one CPU/BLAS thread, `nice -n 19`, and no RF or IQ access. Every outcome
gets a receipt. The input index preserves all 88 identities and the exact frozen
first16 records from wave3; only fully validated new artifacts become ready.
