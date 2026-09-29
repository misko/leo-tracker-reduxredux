# Active-epoch coarse peak scan

This isolated quadratic-gate prototype replaces only the full `11 × n` peak
extraction scan. It visits the sorted active regional epochs in the original
CFO-major/epoch order, reads the unchanged full-grid neighbours, and retains
the original stable peak sort and top-eight NMS unchanged. Inactive epochs are
support-zero `-INFINITY`, so they cannot satisfy the strict local-maximum
predicate.

The component test compares the production extractor with an independent full
grid scan over boundaries, adjacent active epochs, gaps, equal scores,
all-`-INFINITY`, and 101 deterministic sparse mixes. Host and sanitizer units
passed; the ARM binary is cross-built only.

The host704 cohort has exact candidate parity with sealed `arm_gate_quadratic`:
86,439 candidates, zero changed candidates, and zero changed windows. ARM
timing is pending and is the only remaining qualification step.

Evidence: `build-manifest.json`, `builds/*/build-receipt.json`, and
`host704/{summary.json,manifest.json,rows.jsonl}`.
