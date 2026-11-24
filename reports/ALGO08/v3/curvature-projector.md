# Fixed-state joint Doppler ranking on dense and South

Whole-curve projection reproduced the original numerical ranking in both calibration arms on the two saved candidate pairs. It also preferred the dense family whose matched refit was 337 and 341 m less accurate and preferred the original cold winner on the South omitted capture that produced a false fix. Neither comparison supports dropping candidates or replacing cold discovery. [Protocol](curvature-projector-protocol.md) · [Dense receipt](measurements/curvature-projector-dense.json) · [South receipt](measurements/curvature-projector-south.json)

## What the score retains

Use the same observations for both candidates and whiten them with the prepared per-visit radio scale. Remove an unrestricted offset and slope from each curve, then project away exactly the prepared receiver-smooth design shared by that radio's curves. A per-curve constant also removes a common integer alias and the fitted RF coefficient at that one tuning. Use the released sparse orbit projection at the actual fixed endpoint and per-satellite phase reference. The method prices a cheap quadratic on the nominated rows. The original next-stage score also includes learned noise and latent coefficients, prior and determinant contributions, and its own geometry and validity rules. The test separately repeats the cheap diagnostic with the original posterior phases, which already requires paying the original likelihood. [Implementation](curvature_projector.py)

## Dense signed family at matched coordinates

The original hybrid family chooses 63478 for 222 observations on seven RX1 curves. The existing fixed-coordinate alternate assigns those exact observations to 67511 and retains the other observations and roles. Each calibration arm uses the same position for both candidates. One bounded replay stopped at the original signed-state collection port and verified both fixed objective and RF witnesses and every owner identity. It sealed the phase vectors, shared row design, sparse geometry, and original objective witnesses before running the projected score. The source pair, switched curves and coordinates came from full-data outcomes. This is a retrospective sensitivity diagnostic. [Matched signed family study](dense-family-refit.md)

| Calibration | Candidates in order | Original signed objective | Original RF RMS (Hz) | Whole-curve reference-phase score | Changed-curves-only score |
|---|---|---|---|---|---|
| `c = 0` | 63478 / 67511 | 47,330.920 / 47,283.389 | 141.278 / 141.224 | 4,366.385 / 4,322.348 | 260.657 / 260.589 |
| Fitted `c` | 63478 / 67511 | 47,329.602 / 47,281.642 | 141.294 / 141.222 | 4,365.932 / 4,321.700 | 260.659 / 260.589 |

The common layout includes all 4,369 selected observations across 121 curves. It leaves 4,105 score dimensions, with 11 shared smooth directions removed per radio. The seven changed curves alone leave 198 dimensions, with 10 resolved smooth directions. The reference-phase preference is less than 0.03% on the seven curves alone, versus about 1% with the unchanged curves constraining the shared receiver design. Posterior-phase scoring also prefers 67511 in both cohorts. Both labels stayed above the sampled horizon. In the earlier matched refits that used the same full data and bounds, the 67511 alternative worsened horizontal accuracy by 337 / 341 m even though these numerical scores prefer it. [Fixed and refit family outcomes](dense-family-refit.md)

## South transfer at the original cold-prefix states

The independently chosen public South 100 m omitted capture uses original ranked branches 1 and 2. Reconstructing the archived first-refresh zero phase references and their rank identities exactly replays the saved fixed-zero objective at both finite prefix positions. The fitted-`c` objective is a new calculation at the same original two states. The projected comparison uses 281 common observations across 15 curves, with 34 rows changing owners. It retains 229 dimensions across the two radios. No optimizer, region expansion or publication ran on South.

| Calibration | Original next-stage scores, branches 1 / 2 | Reference-phase projection | Posterior-phase projection |
|---|---|---|---|
| `c = 0` | 432.155 / 501.584 | 95.939 / 205.721 | 9.011 / 11.879 |
| Fitted `c` | 442.067 / 509.231 | 95.939 / 205.721 | 8.923 / 11.226 |

Both scores prefer branch 1. The earlier omitted-offer terminal nevertheless published a false fix with 554 / 824 m horizontal error. The fixed states and common roster are based on that saved South packet. South transfers the frozen ranking computation to an independent recording and geometry. It provides no prospective proof against false fixes. [Earlier South outcome](south-raw-offer.md)

## Timing and stop decision

| Stage | Dense CPU | South CPU |
|---|---:|---:|
| Common curve table and reusable projector construction | 10.54 ms | 1.34 ms |
| Whole layout, one arm and two reference-phase candidates | 1.76–2.04 ms | 0.26–0.37 ms |
| Original fixed next-stage evaluation, one arm and two candidates | 130.71–131.14 ms | 4.85–4.90 ms |

The dense hybrid's archived cold discovery used 6.394 CPU s. Removing 2.5 s requires avoiding about 39% of that paid stage, before the cost of generating candidate states and doing the projection. These tests began with original candidate rosters, phase references and locations. They skipped zero discovery work. The dense next-stage clocks include the signed model reconstruction and its genuine diagnostic gates. They price those fixed evaluations, and they do not establish that a few milliseconds after discovery can substitute for the preceding multi-second search. The joint score has no calibrated bound on the original objective over position, phase or alias alternatives, or on the fitted endpoint's error. Keep it as a small proposal-ordering experiment. [Cold-search and calibration evidence](dense-8ms-prefix.md)

The corrected dense and South workers took 20.08 and 3.77 s through exit under the shared Gauss one-core lock. Dense spent 19.449 CPU s recovering the original signed context, with no grid, PNG or original waveform. The first South attempt spent 3.83 CPU s before the installed geometry port rejected nonfinite values on unused bank rows. The dense process in that session was stopped before scoring at 19.79 CPU s. The corrected transport supplies only the actual nominated phase rows. The dense fixed-state capsule subsequently reran all projected scores bit for bit in a separate 0.80 s process, with no position replay and no original data preparation. The saved capsule at `/dev/shm/leo-v3-curvature-shared-result02/dense-fixed-state.npz` has SHA-256 `d5ea12467048f59146f35cba44e16886e83d80975e608333cef73fac05bc40ec`. The scorer has a `dense-score` mode for that capsule. Twelve focused and adjacent tests passed. [Runner](curvature_projector_trial.py)
