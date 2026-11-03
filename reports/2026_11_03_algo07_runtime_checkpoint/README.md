# Runtime development checkpoint — 2026-11-03

This checkpoint preserves the ALGO03 runtime verifier, staging tool and their
tests. It does **not** qualify or deploy a new runtime.

The staging tool requires a committed iteration008 qualification document, which
does not yet exist. It must continue to reject staging until that qualification
is completed. Its source checks currently bind the earlier measured candidate;
they will need a new explicit qualification for any subsequent cache fix.

## Outstanding correctness finding

The independent ALGO03 joint-family replay exposed a prepared-geometry cache
invalidation problem. `audit_two_predictive_families.at_phases` shallow-copies a
family and replaces its phase grid and banks, while `NewFamily.geometry` retains
the old prepared geometry. The candidate's joint c0 audit failed with:

```
ValueError: operands could not be broadcast together with shapes (1,12987) (27,)
```

The preserved diagnostic is under the private benchmark root:
`/srv/bulk/leo/research/algo07-runtime-20261103/algo03-joint/candidate/worker/recovery/joint-c0-audit.log`.
This path is a local evidence reference, not a portable report attachment.

Before promotion, fix cache invalidation, add a shallow-copy regression test,
repeat the joint replay, and compare both calibration arms against the frozen
baseline. A failed audit or fallback must not be counted as a speed improvement.
The overall 10× runtime target remains unachieved.

## Checkpoint validation

The ALGO03 and ALGO07 runtime-release test modules passed together: **7 tests**.
Ruff passed on the three newly preserved files. These tests validate staging and
verification behavior; they do not establish scientific parity of the candidate.

No production service was changed for this checkpoint. Existing large local
benchmark outputs, build trees and historical analysis artifacts are not added
to this commit.
