# Worldwide absolute Doppler from anonymous GLRT

The shared-level receiver and free-intercept control both withheld on all 11 numerical jobs. The shared-level receiver never reached the true geographic basin on the six matched roof recordings or either new simulated site. Across the six roof recordings, its median held RF error was 2.66 kHz with `c = 0` and 2.64 kHz with fitted `c`. Its median forced position error was 16,994 km in both arms. The four original v5 options shared the authentic raw/capture inputs and used a containing tile. Their `c = 0` median position errors were 1.00–1.04 km. [Scores](scores.csv) · [Position charts](charts/manifest.json)

## Receiver and matched controls

The receiver links anonymous GLRT peaks by elapsed time with no prior owner and propagates the causal catalogue. Each spatial hypothesis shortlists six horizon-compatible TLEs per arc from head-only shape with a bounded ±18 s orbital phase. The shared model combines wrapped level across carriers on the same physical receive path. Its four possible clock groups are RX × low/high RF band. Different RF bands are allowed independent offsets. It holds a single integer lift per continuous arc. No clock drift term or learned site coefficient enters the search. The clock gauge is circular with one period of 227,272.727 Hz from the 4.4 µs pilot symbol. The frozen protocol contains a numerical typo for this period. The hashed receiver and native constants use 227,272.727 Hz throughout. [Protocol](PROTOCOL.md) · [Implementation and transitive source hashes](source-lock.json)

The free-intercept control searches with the same peaks, orbit states, shape/phase shortlist and spatial budget. Each arc gets an independent constant that absorbs the RF slope exactly. Each method freezes its chosen owners, orbital phases and integer branches across calibration arms. The shared method estimates `c` only when a same-path carrier contrast exists. Each orbit/phase candidate is ranked on early points and checked on late points from the already linked arc. This measures held RF prediction conditional on anonymous linking. The publication decision also requires a separated finalist and matched held support in both arms. [Sealed prediction rows](positions.jsonl.gz) · [Prediction digests](prediction-lock.json)

The first two archived recordings are diagnostics. The four hash-selected reserves are DS26-0261, DS26-0168, DS26-0114 and DS29-0519. DS26-0070 and DS29-0316 use genuinely omitted archived offers. The workers never received an offered area, a site coordinate, v5 assignments or v5 positions. Offers define the geographic scoring conditions only. Each of the two new simulated sites contributes a containing and an omitted score from the same numerical prediction. The separate +120 s orbital-time control reuses the exact DS26-0122 GLRT and catalogue. The prepared public StarLoc beacons choose and sometimes harmonically reindex a tone per pass, with no verified cross-arc absolute carrier reference. Those records therefore do not support this clock-level test. [Bound inputs](blind-plan.json) · [Released simulation seed and labels](synthetic-truth.json) · [StarLoc frequency contract](../../inference/physical-differences/README.md)

## Actual attempts

Errors below are medians. RF columns report early conditional and late held RMS separately in Hz. Forced locations are solver outputs that failed publication. The two simulated sites are counted once each. C0 and fitted arms use the same job and distinguish nuisance calibration only.

| Cohort | Model | Published / numerical jobs | Forced km, c0 / fitted | Train RF Hz, c0 / fitted | Held RF Hz, c0 / fitted |
| --- | --- | --- | ---: | ---: | ---: |
| Six roof recordings | Shared level | 0 / 6 | 16,994 / 16,994 | 1,565 / 1,480 | 2,662 / 2,642 |
| Six roof recordings | Free arc intercept | 0 / 6 | 6,678 / 6,678 | 147 / 147 | 1,056 / 1,056 |
| Two true omitted offers | Shared level | 0 / 2 | 11,537 / 11,539 | 1,532 / 1,306 | 2,004 / 1,802 |
| Two true omitted offers | Free arc intercept | 0 / 2 | 14,947 / 14,947 | 163 / 163 | 845 / 845 |
| Two simulated sites | Shared level | 0 / 2 | 11,917 / 11,920 | 949 / 788 | 1,698 / 1,329 |
| Two simulated sites | Free arc intercept | 0 / 2 | 10,492 / 10,492 | 59 / 59 | 387 / 387 |
| One +120 s control | Shared level | 0 / 1 | 1,130 / 1,130 | 1,371 / 1,386 | 1,853 / 1,883 |
| One +120 s control | Free arc intercept | 0 / 1 | 10,846 / 10,846 | 139 / 139 | 1,032 / 1,032 |

All records include a forced coordinate and none timed out. In the +120 s control, the shared forced solution moved closer to the real receiver while held RF error increased from 1,628 to 1,853 Hz in the c0 arm. On both simulations, neither solver selected a single truly emitting NORAD. Fitted `c` reduced shared held RF at both simulations without improving median geography. [Per-record calibrations and outcomes](scores.json) · [Original and simulated offer bindings](blind-plan.json)

## Coverage and cost

The 192-point, site-free global mesh was refined around four training-ranked hypotheses per method. The combined search evaluated 400–448 distinct positions per job. The nearest position in that combined ledger remained 363.4 km from the real roof and 424.2/602.2 km from the two simulated sites. The refinements selected by either method never improved on the global mesh distance at any tested physical position. The comparison with v5 includes the practical value of the authentic regional offer alongside differences in the estimator. Near-site absolute CFO observability remains unresolved because the worldwide search missed all three physical positions. [Per-case coverage and original v5 references](scores.csv)

The standalone receiver module is 348 lines including comments and blank lines. Its stages are anonymous linking, causal propagation, circular or free-offset ranking with worldwide refinement, and matched calibration with held validation. It processed 10–16 selected arcs per job. The paired worker shared its orbit and spatial scan across the two methods, with 10.06 s median and 11.22 s maximum CPU time. End-to-end from the saved native document took 17.58 s median and 31.88 s maximum wall time on a shared host. Peak RSS was 281–300 MiB. These are paired-job costs. The original four v5 roles are endpoint references and no same-boundary runtime speedup is asserted. [Timing and memory by job](scores.csv) · [Frozen source closure](source-lock.json)
