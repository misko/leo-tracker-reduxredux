# DS6 track influence and single-track deletion

Simple track pruning is not supported by this diagnostic. Removing a high-
influence track changes position substantially, but none of the tested
deletions takes a previously failing development scan below 1 km. Every one
of the 24 deletions worsens prediction of the omitted track's held observations.
No rejection rule or new location estimator is adopted.

| Sample rate | Corrected baseline error, km | Range across six diagnostic deletions, km |
|---|---:|---:|
| 2.5 MS/s | 3.670 | 3.326–4.023 |
| 5 MS/s | 8.482 | 7.082–9.699 |
| 7.5 MS/s | 0.505 | 0.329–1.023 |
| 10 MS/s | 4.950 | 4.471–5.496 |

These ranges show sensitivity, not a selection policy. In particular, the
0.329 km result must not be chosen using its favorable geographic error.
Five of twelve high-influence deletions improve geographic error, as do five
of twelve random-control deletions. High influence does not identify a faulty
track. Their median position shift is 1,121.99 m, versus 145.94 m for controls.

The four scans are the previously frozen rate-representative development
cohort. All use the corrected causal orbit elements and rebuilt candidate
shortlists. At each frozen baseline training winner, central finite differences
of track mixture losses estimate gradients and observed information in east,
north and scan timing. The linearized deletion shift includes the small
nonzero total baseline gradient. Singular/non-positive information is explicit
and would rank first for inspection; none occurred on these scans.

For each scan, the three largest predicted horizontal influences and three
other tracks selected by hash seed 2026092737 are frozen before geographic
evaluation. Two starts fit each single-track deletion using retained training
observations alone. The original random whole-visit training/held masks and
the same Student-t4 scale, track-offset profiling, candidate mixtures and
position/timing bounds remain in place. No ground-truth coordinate appears in
the fitting script.

The omitted-track diagnostic profiles that track's constant frequency offset
using its training visits at the already-fitted location, then scores its held
visits. Those omitted observations never change the position estimate. This
is conditional prediction of omitted trajectory shape, not prediction of an
unknown absolute transmitter frequency or an independent scientific holdout
unaffected by prior development use.

Halving the derivative steps changes predicted shifts by at most 3.84 m for
selected tracks. All actual fits remain inside bounds. Twenty-three selected
winners report convergence; one 2.5 MS/s influence deletion reports abnormal
line-search termination. Its other start converges only about 0.12 m away,
with a training-score difference of 0.000001. Both statuses and results remain
unchanged; the warning is not hidden or relabelled. It cannot account for the
kilometre-scale failure of this diagnostic to solve the bad scans.

Three tests passed: finite-difference information and deletion shifts against
an exact synthetic quadratic solution; singular-information handling and
deterministic, disjoint selection; and all-four provenance, selection and
exact-propagation checks. Exact versus interpolated predictions differ by
less than 0.05 Hz. `summary.json` hashes the completed outputs and the separate
operator-reference authority; `deletions.csv` reports every tested deletion.

The corrected joint estimate remains 761.85 m, with the same random scan
subsets at 941.20 m and 649.88 m. Independent-scan performance remains 6/43
below 1 km. This experiment does not change those accepted estimates. The
next investigation should address errors shared across a whole track or
transmitter, rather than declaring a track invalid because it has influence
or because deleting it moves an estimate toward the known reference.
