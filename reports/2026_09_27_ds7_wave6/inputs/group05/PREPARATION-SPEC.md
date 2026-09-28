# Wave 6 chronological group8-05 preparation

This specification precedes persistent execution. This worker owns only chronological captures 033--040 (`group8-05`), report artifacts below `reports/2026_09_27_ds7_wave6/inputs/group05/`, and generated banks below `.leo/ds7-wave6/group05/`.

The immutable predecessor is `reports/2026_09_27_ds7_wave5/inputs/inputs-first24-group8-03-ready-v1.json`, SHA-256 `cfedef0e5601845665184f993123d30e3af2bc27edc87815f9ae709fc5b424b6`, containing 32 ready rows. Progressive indexes derive from the corresponding unfrozen index, SHA-256 `fb6d9098837f6e87529a5b13f7a9c64c0bb1afbd5ffc0ca2877bca652b74f86c`. Every snapshot must retain all 88 identities and manifests, preserve those 32 frozen records exactly after freezing, and add only successfully validated captures from 033--040.

Preparation uses unchanged `tools/ds7_combined_export.py` (`6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`) and the Wave 4-closed original exporter. It uses cached public source and orbit archive ports only. No RF collection, raw IQ, score, reference, pose interpretation, or production/source mutation is authorized.

One persistent root-owned controller receives a 1,200-second whole-worker deadline. Every capture subprocess receives at most 240 seconds. The controller and its descendants inherit a 3 GiB address-space ceiling, one CPU/BLAS thread, and nice 19. It stops on a capture failure or exhausted lease, retains partial artifacts, never overwrites an attempt, and writes terminal accounting. This worker may overlap only the separately leased group-04 preparation and at most one fitter.

The ordered capture identities are:

1. `scan-fw-0559bed89e34ddd4`
2. `scan-fw-e49d644f35f4b3a9`
3. `scan-fw-40a5442f036ce35a`
4. `scan-fw-c63f009ab3db5f14`
5. `scan-fw-53b91e4383b99797`
6. `scan-fw-c644746d01db758f`
7. `scan-fw-43e84176a367910b`
8. `scan-fw-64cadc7111299819`

Each successful capture produces a track export, candidate manifest/shortlists/bank, combined-export receipt, progressive 88-row index, and sealed progressive input contract. The controller validates actual artifact hashes, exact old-row preservation, ready counts, and new identity coverage before advancing.
