# The displayed coarse scores include changes made after refinement

DS18-022 has 400 original ordinary coarse receipts, all retrieved through the
public checkpoint reader. Five scores in iteration107's displayed search trace
are lower than the scores that actually drove the original search. This is
documented post-search recovery behavior, not evidence that the saved queue ran
with those improved scores.

| Point east, north (km) | Original queue score | Displayed post-recovery score | Displayed minus original |
|---|---:|---:|---:|
| −200, 40 | 32762.045853 | 32520.342158 | −241.703694 |
| 0, 160 | 33173.473175 | 32839.421024 | −334.052152 |
| 0, 80 | 31348.391312 | 30475.981745 | −872.409568 |
| 160, −120 | 32985.298705 | 32922.622036 | −62.676668 |
| 200, 0 | 31796.055718 | 31781.712968 | −14.342751 |

There were seven recorded coarse recovery attempts; the other two kept their
original endpoint and score. All seven original and displayed fit digests are
retained in [coarse-import.json](coarse-import.json), including unchanged cases.
These coordinates are the complete metadata-defined changed set, not locations
selected by reference distance.

## Source proof and exact replay

[hard60_runner.py:145](../../src/leo/application/hard60_runner.py#L145) executes
the hierarchical search before constructing the result and calling recovery
at [line 286](../../src/leo/application/hard60_runner.py#L286).
[hard60_recovery.py:43](../../src/leo/application/hard60_recovery.py#L43) identifies
unqualified 40 km fits; the bounded fitter starts from the original bootstrap
vector. It chooses an improved feasible endpoint by model objective at
[line 78](../../src/leo/application/hard60_recovery.py#L78), then reranks regions.
At [line 249](../../src/leo/application/hard60_recovery.py#L249), it explicitly
updates presentation copies of point fits and search scores. The original
immutable checkpoints and `recovery.coarse[].original` remain available.

The importer initially stopped when given the displayed scores: its 1e-6 parity
gate correctly rejected the five mismatches. Trying the research checkpoint
overlay did not resolve the distinction; the change is in the returned
presentation result, not a replacement of the immutable original point receipt.
No mismatch was waived and no alternative endpoint was selected by error.

After restoring the original scores from the recorded recovery provenance,
every original recovery fit matched the public checkpoint's **entire fit
digest**, not merely its objective. All 400 public receipts matched the restored
score inventory. A deterministic replay of the hierarchy using **only these
saved scalars** reproduced all 400 coordinates, spacings, scores and their order
exactly. This performed no recording reconstruction, orbit propagation,
objective evaluation or numerical fitting.

## Frozen-input preparation artifact, not a frozen experiment

The receipt bundle contains all 400 original bootstrap/fit payloads, raw payload
digests, seed/fit vector digests, the whole-prior bank's **877** ordered satellite
IDs, restored queue trace, and post-recovery provenance. It also binds the
iteration107 baseline receipt's file digest and protocol identity.

- File: [coarse-import.json](coarse-import.json)
- Size: 4,723,837 bytes
- SHA256: `ab1c2d6c374307cad67c4492175a9ff5913963fa3d0d1a24718510bfacfc044c`
- Missing/failed source payloads: 0/400. This does not mean every fit was
  independently converged; original convergence flags are preserved.
- Historical numerical source identities match. The previously approved
  non-numerical `application/regional_position_report.py` mismatch is disclosed
  separately and does not authorize other source differences.

## Consequence for iteration116

The approved scope is explicitly a **pre-recovery queue-allocation comparison**.
Both search policies use original ordinary coarse endpoints and the same
ordinary fit policy for newly sampled coordinates. No post-search recovered
endpoint is injected into the refinement queue. Imported fitted-c endpoints
reuse historical computation; zero-c receives fresh fits under matching
per-point limits and shared bootstrap starts. This is not four fresh equal-time
searches.

The experiment may compare queue allocation and raw score-led retention. It
cannot call its raw retained regions the deployed post-recovery winners, and it
cannot claim a localization improvement from this search-only comparison. A
separate matched post-search recovery, calibration, association and final-fit
continuation is needed before a position result. Reference coordinates remain
evaluation-only throughout.

The experiment is **not frozen**. Full reconstructed observation/bank/prior
hashes still require an authorized preflight once numerical capacity is free.
No fabricated array hashes, new recordings or additional pilot members are used.
