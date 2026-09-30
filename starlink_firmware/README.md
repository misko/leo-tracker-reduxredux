# Starlink firmware reverse engineering

[apk_fw_v1](apk_fw_v1/README.md) is the first APK-derived dish-firmware research
workspace. Keep later acquisitions in separate versioned directories so binary
addresses, hashes and conclusions stay tied to their source corpus.

## September 30 publication: reading guide

- [RF receive path and message handoff](apk_fw_v1/reports/2026_09_30_rf_receive_trace/README.md)
- [Internal image extraction, including the six XP70 S-record images](apk_fw_v1/reports/2026_09_30_rf_receive_trace/UNPACKED_IMAGES.md)
- [Executable, function and call-site atlas](apk_fw_v1/reports/2026_09_30_firmware_atlas/README.md)
- [Fresh firmware audit and clustering associations](apk_fw_v1/reports/2026_09_29_firmware_cluster_reaudit/README.md)
- [Recovered symbols and clustering](../reports/2026_09_29_all_track_symbols/README.md)
- [DS10 signal extension](../reports/2026_09_29_ds10_signal_extension/README.md)
- [Identity hypotheses and controlled experiments](../reports/2026_09_29_identity_resumption/README.md)
- [Kutkov source review and download catalog](../docs/research/oleg-kutkov/README.md)

This publication contains research code, component tests, conclusions, and source
provenance. Downloaded firmware, papers, recordings and generated numerical data
remain local. Previously published historical report directories are retained.
References into `local/` describe available research inputs; they are not files
bundled in Git. Firmware addresses and synthetic message experiments do not by
themselves establish a mapping from received RF bits to satellite identity.

Publication validation: 315 tests passed for the firmware reports, source collector,
symbol/DS10 experiments, T-code mapping and native-rate decoder; 14 identity
experiment tests passed in a separate process to avoid colliding historical module
names. The tests used the existing local firmware corpus. Collector lint also
passed. No new RF collection or deployment was performed.
