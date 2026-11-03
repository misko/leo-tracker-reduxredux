# Metadata-only catalogue coverage prototype

The response-blind full-capture bank contains 845 potentially visible STARLINK
IDs, including all 40 original full-data selected IDs and all 25 training-only
cold-selected IDs. After freezing the bank, the descriptive label audit found
that all 1,410 original held-half assignments have their original winner ID in
this bank. This removes the demonstrated selected-ID availability ceiling; it
does not demonstrate a single additional predicted assignment, correct identity,
frequency fit or geographic improvement. No localization, calibration, timing,
detection-probability or CFO likelihood fit was run.

## Frozen eligibility policy

Use the same causal S03 SPACE-TRACK archive snapshot:
`d07c22e355ffbe4699bc4be9de9f330c0eef3e44b74f6d200b1cb14502dffbe7`.
Its receipt retains the original provider, collection timestamp and strict
origin-minus-505-second cutoff. Keep the existing 250 km regional prior, without
using a fitted point or station reference. Project only observation ID, capture
time, actual RF, receiver and channel metadata from the frozen recording export;
measured CFO is replaced with zero and signal margin with one before passing
observations to the public regional bank API.

Apply the public explicit STARLINK-debris filter and retain catalogue entries
whose names begin STARLINK. The public regional bank propagates the whole known
capture at 0.25 s spacing with 21 s padding on each side, then screens with a
conservative bound over every geodetic normal in the regional prior. The padding
preserves the existing timing-shift support and interpolation margin. This is
potential horizon eligibility, not evidence that an object emits the measured RF
or serves the receiver.

Actual RF values are preserved and bound in `freeze.json`. The public TLE
catalogue has no per-transmitter RF-support authority, so no invented RF-band
filter or per-satellite frequency exception is introduced. Radio and oscillator
frequency compatibility remain unproved.

A fixed cap of 1,024 was declared before this prototype, using the next power of
two above the previously measured 708 training-regional candidates. If needed,
membership ranks by potential whole-prior visible-node count, then maximum
conservative horizon margin, then catalogue number. These quantities use only
orbital geometry and the broad prior. The cap is inactive here; there is no
post-audit cap change or manual satellite insertion.

| Eligibility accounting | Count |
|---|---:|
| Input catalogue entries | 11,149 |
| Explicit labelled STARLINK debris excluded | 0 |
| Other catalogue names excluded | 0 |
| STARLINK entries propagated | 11,149 |
| Invalid propagation excluded | 0 |
| Outside whole-prior visibility excluded | 10,304 |
| Geometrically eligible before cap | 845 |
| Cap exclusions | 0 |
| Frozen retained IDs | 845 |

Rejected/invalid IDs, all geometry scores and bank hashes are retained in
`freeze.json`; full states are in `metadata-bank.npz`. `freeze.json` and the bank
are persisted before loading saved selected-ID lists or original assignment
labels. `overlap.json` binds that freeze and contains the later descriptive
coverage audit. Original labels are full-data conditioned and are not truth.
All 1,681 original training assignments are also covered, as are both original
selected banks. This is a coverage ceiling diagnostic only; neither the enlarged
bank nor its labels were fed into the point classifier.

## Measured cost and model implications

The single prototype took 5.92 s total, including 4.50 s of bounded propagation;
the regional API cap was 90 s. The 845 × 1,369-node position/velocity bank uses
52.95 MiB of float64 state arrays and a 50,926,382-byte compressed NPZ. There are
3,988 known observations, so a future dense full-recording evaluation would have
3,369,860 observation-candidate pairs. Each scalar float64 N×K array alone is
25.71 MiB; spatial derivatives use two such planes, and a full objective needs
multiple additional arrays. These are array-size estimates, not measured solver
peak RSS or fitting runtime. Pairwise arithmetic scales to 33.8 times the cold
25-ID bank or 21.125 times the original 40-ID bank, before any implementation
changes. Propagation speed does not establish fitting speed.

Do not pass 845 lines to the old point classifier and call greater best-match
coverage a recovery. Numerous independent lines increase chance frequency
coincidences, and strict parameter stationarity does not imply identity
confidence. The lean next model to study is a **normalized population/birth
branch** for training-unsupported but metadata-eligible candidates, preserving a
declared total signal mass and requiring coherent track evidence. It should
retain the existing identified-track branch, shrink unsupported timing to its
population prior, and be tested against a time-permutation control and the old
hard selected-ID policy on matched held blocks. This prototype does not implement
that branch, allocate 845 independent free timing/q coordinates, tune its prior,
or establish its usefulness.

## Tests and boundaries

Three hardware-free tests pass: forbidden measured-CFO/station fields raise if
accessed but metadata projection succeeds; arbitrary CFO and station-reference
perturbations leave metadata unchanged; and deterministic geometric capping
preserves membership under candidate permutation. The projection deliberately
has no station-reference or signal-response argument. Prior translation can
legitimately change eligibility and is not required to be invariant.

Only existing read-only archive/public regional APIs and frozen report inputs
were used. No RF, other recording campaign, production change or change to sealed
reports. This is one candidate-eligibility prototype, not a fitted-c/c=0 model
comparison; a future fitted model still requires that controlled ablation.
