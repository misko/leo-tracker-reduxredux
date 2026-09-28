# Wave 5 preparation specification

This separate bounded lease prepares chronological plan captures 017–024, in that order. The frozen Wave 4 final input is the immutable predecessor; all 88 identities and its 24 ready records are retained exactly, and only successfully validated new records become ready.

The implementation is unchanged `tools/ds7_combined_export.py` (`6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`), using unchanged exporter `tools/ds7_export_baseline.py` (`4d2e4bb96e687ca9fe1a035c138c87e55d2976d0136bffac182b1bc380c42dc4`) and input freezer `tools/ds7_eval.py` (`6f8b067f64032e32003874cc1e0dd86ad9d3bc74360fe11ac15c9230687fa208`), matching the Wave 3 closeout bindings.

One root-owned controller has a 1200-second wall cap. It invokes one serialized source read at a time, with each recording capped at 180 seconds, `nice -n 19`, and one CPU/BLAS thread. It uses only cached public ports; no raw IQ or RF collection is authorized. A generated receipt is retained for every completed operation, and a terminal receipt will distinguish controller wall time from summed recording reports.
