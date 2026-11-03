# Fixed-bank initialization changes the solution, but does not recover the hard windows

Two existing complete S01 states were transported into the **same causal Space-Track 59-candidate target** and fitted with identical observations, neutral initial detection probabilities, model, priors, broad regional domain and search allowances. All four outcomes are strict. The states remain in substantially different solutions: the ST donor gives better whole-scan support and a lower common objective, but recovers fewer requested observations. Neither recovers DSX01-003. This is not a successful general recovery policy.

## Matched target and budget

| Donor start | RF arm | Full assigned /4,797 | Requested /148 | J | Data NLL | Configured-reference km | Strict |
|---|---|---:|---:|---:|---:|---:|---|
| Original HF state | fitted c | 1,858 | 29 | 60,105.695 | 59,463.856 | 116.353 | yes |
| Saved ST state | fitted c | 2,170 | 13 | 58,347.358 | 57,830.858 | 8.084 | yes |
| Original HF state | c=0 | 1,850 | 32 | 60,254.284 | 59,624.380 | 116.956 | yes |
| Saved ST state | c=0 | 2,166 | 11 | 58,478.769 | 57,963.843 | 8.423 | yes |

Every row uses ST59 ephemerides during inference; “HF state” describes only its donor. Comparing the fitted-c ST start against the matched HF start adds 1,217 and loses 905 whole-scan assignments, a net +312. Among their 953 retained observations, 893 change model identity; paired frequency RMS changes 155.95→138.61 Hz. Requested support adds 10 and loses 26, net −16. Point counts are not verified satellite labels, and changing-population RMS cannot establish better physical assignments.

The original historical HF46 endpoint has 1,643 full and 14 requested assignments, while the historical ST59 endpoint has 2,150 and 17. These historical pipeline runs differ in discovery, provider, initialization, q and upstream cost; they are descriptive anchors, not budget-matched controls. The four new rows isolate **combined initialization conditional on ST59**, not provider accuracy, candidate-discovery causality or geography alone. The two donors are the pre-existing complete provider runs; neither was chosen from a new search by station distance or challenge recovery.

## Every tested window

| Window | Original | Saved historical ST | HF start, fitted c | ST start, fitted c | HF start, c=0 | ST start, c=0 |
|---|---:|---:|---:|---:|---:|---:|
| DSX01-001 /86 | 13 | 14 | 20 | 9 | 25 | 6 |
| DSX01-002 /35 | 1 | 3 | 9 | 4 | 7 | 5 |
| DSX01-003 /27 | 0 | 0 | 0 | 0 | 0 | 0 |

The other four sources, 12 windows and 545 requested observations are untested by this assay. There is no all-five recovery aggregate, per-window winner combination, or sub-kilometer claim. Even the nearer ST solution remains about 8 km from the configured reference. Configured roof coordinates have unknown survey/altitude uncertainty and were read only after all four outcomes sealed; they do not initialize or select a fit.

![All three fixed-denominator windows](windows.png)

![Frequency-support and one-source position curves](performance.png)

![Timing histogram and complete position diagnostics](timing_and_position.png)

## Exact state transport and verification

The original and target states share all ordered winning observations, actual RF metadata, calibration design, residual-clock basis and regional coordinate frame. The five physical calibration coefficients, all residual-clock coefficients, and each receiver's absolute high-band function carry exactly. The actual-data correction closure is saved for every arm. Different satellite banks do not enter that calibration identity.

Original and target banks share 34 identities; 12 original-only candidates are dropped and 25 target-only candidates receive the donor common timing. Overlapping total timings remain unchanged. The target common mean and orthonormal zero-sum coordinates are recomputed without shifting the overlap or clipping physical values. The existing solver's at-most-nanosecond timing-bound interiorization is disclosed in qualification, with a fixed 2e-9 rejection guard.

Both starts use identical neutral q=1.6/59 and zero detection coordinates. This deliberately removes donor-q initialization differences; q is then free in both fits. Absolute receiver-band offsets are free with their existing 50,000 Hz prior once. Clock, q, physical, common/relative timing and original constraints remain unchanged. Both use the broad 250 km regional disk, without donor-specific extra production 25 km disks. c=0 only removes the donor RF coefficient before transport and fixes it during fitting. Discovery/donor construction used fitted c, so it is conditional sensitivity, not a cold c=0 pipeline.

Eleven transport tests and two paired-evaluation tests pass. Actual qualification includes native frozen/joint J, NLL, physical/nuisance gradients and posterior nesting; all four seed calibration/timing/q/domain checks; and both band derivatives at every seed. All four complete v/n seeds are durable in `qualification.json` before fitting. Independent review found no mathematical blocker, and its seed-freeze/cost-accounting observations were incorporated before launch. Ruff passes for the owned code.

Each fit receives 1,000 objective calls and 120 active seconds. Actual counts are 596/660/479/488 (2,223 total), taking 29.60/32.58/23.67/24.15 s. Source preparation, 22 qualification objective calls, two public endpoint-replay calls and four independent terminal audits are additional and explicitly separate. Whole preparation/qualification/four-fit execution completed in 131.79 s under a single-worker external 600 s TERM/605 s KILL cap. No extra fits, profiles, retries, threshold changes or post-failure finishing were applied. Post-seal evaluation used six classification objectives plus two public endpoint-replay calls and read-only preparation.

`source_freeze.json` pins owned/public source and input authorities. `qualified_freeze.json` binds late-loaded public dependencies and qualification before inference. `outcomes_seal.json` freezes all four raw fits before `evaluation.json`, window evaluation or station-reference access. NPZ exports retain original observation IDs, times, model identities, assignment masks, residuals and row NLL. Original DSX membership/context hashes match the earlier sealed comparison authority. No production write, remote publication, RF collection or older-evidence mutation occurs.

The result supports two conclusions: initialization affects which solution the model reaches, and the lower-objective/nearer solution still fails these requested trajectories. Another geographic start alone is therefore insufficient. The separate all-five identifiability audit establishes substantial local calibration/timing confounding, but neither result identifies the physical cause of the missing trajectories.
