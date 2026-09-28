# Correction to first-eight metadata audit

This correction supersedes the RF-scaling paragraph in
`FIRST8-METADATA-AUDIT.md` only. The original export audit correctly found that
the final exporter copies `measured_cfo_hz` verbatim from the reconstructed
graph, but its conclusion about upstream normalization was incomplete.

The persistent-hop trajectory path normalizes native candidate CFO to the fixed
11.2 GHz convention using actual RF and relative alias handling before it
becomes graph `measured_cfo_hz`. The exported observations are therefore
canonical-frequency measurements, consistent with the bank's fixed-11.2 GHz
prediction convention. Existing banks remain valid and unchanged.
