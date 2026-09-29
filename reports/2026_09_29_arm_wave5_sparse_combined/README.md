# Wave5 sparse active-peak extraction

This sealed derivative of `arm_wave5_combined` changes only coarse peak
extraction: it visits sorted active regional epochs while keeping the original
grid neighbours, CFO-major/epoch order, stable sort, and top-eight NMS. Raw
direct CI16 ingestion, the .312 rate gate, quadratic block-64 conditioning,
and FP64 final GLRT are inherited unchanged.

Host and sanitizer pass inherited raw-direct, rate-gate, final-reuse,
fine-budget, moment, and active-extraction reference tests. The extractor test
covers boundaries, gaps, equal values, `-INFINITY`, and deterministic sparse
inventories against a full-grid reference.

Exact candidate parity passed on host704 (86,439 entries) and both 32-dwell
DS8 (3,624) and DS9 (3,689) panels. ARM is cross-built only; timing is pending.

Evidence: `build-manifest.json`, `builds/*/build-receipt.json`, `host704/`,
`host-ds8/`, and `host-ds9/`.
