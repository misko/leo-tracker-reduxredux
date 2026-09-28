# Proposed next receiver-geometry confirmation cohort

## Proposal

Use the four remaining cache-ready roof recordings that share pose revision
`gauss-r20-roof-20260926-v1` after excluding every session in the ten-record pilot and
four-record first confirmation panel. The deterministic rule is metadata-only: select all
remaining rows with a hash-verified public `TrackingInput` cache and that pose revision,
ordered by capture start and session ID.

| Capture start UTC ns | Session | Rate | Historical exposure |
|---:|---|---:|---|
| 1790480791865151399 | `scan-fw-609d7a8d9861f3db` | 5 Msps | Roof geometry confirmation |
| 1790482490527149904 | `scan-fw-53ce822d78d476ba` | 10 Msps | Roof balanced confirmation |
| 1790482915221767372 | `scan-fw-e76c229e9dc498b3` | 5 Msps | Roof balanced confirmation |
| 1790483338777911208 | `scan-fw-c9db23377d1194dd` | 10 Msps | Roof balanced confirmation |

All four were previously inspected and analyzed in other research. They are disjoint from
the current study's 14 recordings, but they are not unseen or blind observations. The
selection did not read candidate, residual, association, or score fields.

## Limits of available coverage

This panel covers 5 and 10 Msps twice each. No unused, cache-ready 2.5 or 7.5 Msps roof
recording with the same pose revision remains in the inventoried derived corpus after the
14 current-study sessions are excluded. Filling all four rates would therefore require
preparing another existing recording or relaxing the pose/readiness requirements; neither
is part of this proposal.

DS8 is chronologically preferable and its minted manifest contains 65 complete post-DS7
recordings across all four rates. The metadata inspection found no corresponding public
`TrackingInput` pickle inventory for those DS8 recordings. The DS8 manifest describes raw
published captures, so it is not sufficient evidence that the current derived-cache pipeline
can consume them. This proposal therefore does not claim a post-DS7 cohort.

## Readiness and provenance

Each proposed cache exists and its bytes match the recorded SHA-256. Each row has exact input
and analysis manifest hashes, capture bounds, sample rate, visit/probe counts, pose binding,
and public persisted contract `leo.contracts.scanner_tracking.TrackingInput`. The pose is the
same provisional roof fixture used in the current work: 37.849056280893684 N,
-122.48575489722863 E, nominal east/west receiver directions, with no measured RF phase-center
baseline.

[`confirmation-proposal.json`](confirmation-proposal.json) is the machine-readable proposal
and binds the two current datasets, the consolidated geometry inventory, and the DS8 manifest.
It is a selection receipt only. It does not mint a dataset, alter configuration, authorize RF,
or run the confirmation analysis.
