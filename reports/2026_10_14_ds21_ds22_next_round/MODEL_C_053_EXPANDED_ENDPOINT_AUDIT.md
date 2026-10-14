# C053 expanded endpoints: calibration transfer diagnostic

The full-band state has lower full-band objective than either half-band state
when all parameters are transferred unchanged. This is not evidence that its
position is preferable: half-band calibration is not constrained by the omitted
band. Position and nuisance effects must be separated before interpreting this
as a geographic likelihood conflict.

| State scored on unchanged full likelihood | Full objective | Low NLL | High NLL | Prior |
|---|---:|---:|---:|---:|
| Full endpoint | 22885.711905 | 15456.541517 | 7182.844436 | 246.325953 |
| Low endpoint | 24993.342761 | 15407.883701 | 9352.492401 | 232.966659 |
| High endpoint | 27250.820947 | 20172.019211 | 6851.983410 | 226.818326 |

At the low endpoint, low likelihood improves by 48.657815 while high likelihood
worsens by 2169.647965. At the high endpoint, high likelihood improves by
330.861025 while low likelihood worsens by 4715.477694. In that latter transfer,
low-band signal posterior mass collapses from 909.228185 to 109.030548. The
opposite-band loss is spread across channels, consistent with incompatible
unprofiled calibration. It cannot yet be assigned to receiver geometry.

The audit reconstructed exact native posteriors at all three endpoints and
verified own-view score replay and low/high likelihood closure. It made twelve
objective evaluations, three explicit orbit calls, zero fits, and no reference
read; runtime 10.795 seconds. The component test covers actual native view
partition and rejects altered saved objectives. Ruff passed.

Next controlled test: hold each of the three training-derived positions fixed,
initialize every nuisance parameter from the same full-band endpoint, and fit
the identical full-band objective. This isolates nuisance reoptimization from
geographic movement and avoids choosing anchors from the reference position.

Source `64c427439`; namespace
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-expanded-endpoint-audit-053-v1`.
Result SHA256 `cdd2fe905b4a8c684ff0dc3d9d89a748afccfbb3112bd1cf295785dbf327d49b`.
Seal SHA256 `fdf8a16102a0a4cadae319391afb868fa56c2e6ccd90ea82e8d9af5fc62cc476`.
