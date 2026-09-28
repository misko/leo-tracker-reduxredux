# Wave 6 Group 04 preparation specification

This independent worker prepares chronological captures 025–032 only. It starts from Wave 5's unfrozen 32-ready index and final frozen digest `cfedef0e5601845665184f993123d30e3af2bc27edc87815f9ae709fc5b424b6`; every progressive index preserves its 88 identities and 32 existing ready rows exactly.

The unchanged combined exporter (`6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`), baseline exporter (`4d2e4bb96e687ca9fe1a035c138c87e55d2976d0136bffac182b1bc380c42dc4`), and input freezer (`6f8b067f64032e32003874cc1e0dd86ad9d3bc74360fe11ac15c9230687fa208`) match Wave 4 closeout bindings. Scientific parameters are unchanged.

One root-owned controller has a 1200-second cap, an inherited 3 GiB address-space limit, and invokes one capture at a time with a 240-second cap, nice 19, and one CPU/BLAS thread. Source access is read-only; no raw IQ or RF collection is permitted. Generated receipts, controller status, and a terminal receipt preserve every result.
