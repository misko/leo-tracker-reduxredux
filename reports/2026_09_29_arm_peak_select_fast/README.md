# Rejected exact coarse-peak selection prototype

The original `arm4-diagnostic` is invalid as an optimization comparison: its
coarse FP32 header differed from Wave4, and its ARM exact-candidate assertion
failed. Its original copied receipt and exact source snapshot are preserved
in publication archives solely as failure evidence.

Local `builds-v1/` is a later unqualified reconstruction, not that original
build. Its runner matches the diagnostic runner hash, but its unit-test source
and binary differ from the original diagnostic receipt. Its own reconstruction
source hashes have been restored and verified. It must
not be executed, combined or used as a source base. Publication explicitly
excludes this reconstruction while retaining the original diagnostic receipt
and all original source hashes, including test source `4f51c37d…f3f`.

`builds/` is the sealed valid v2. Its source inventory differs from Wave4 only
in `full_search.c` and the new `test_retain_peaks.c`: an exact stable linear
top-eight selection replaces the full coarse-peak sort. Host and sanitizer
units compare it to an independent stable reference over 257 mixed/tie/wrap
inventories. The valid ARM unit passed. Both host704 and ARM-v2 have exact
candidate parity and frozen standard audits.

The v2 ARM mean fused dwell time was 1,692.752 ms, versus the Wave4 mean
1,686.498 ms. It is 6.254 ms slower, so the prototype is rejected and must
not be combined with other variants.

Evidence: `build-manifest.json`, `builds/*/build-receipt.json`,
`host704/`, `arm4-v2/`, `arm-units-v2.json`, and their
`standard-audit.json` files.
