# Native frequency contracts: synthetic findings and remaining incidence gate

The independent carrier contract test passes. The native and Python kernels use
each observation's recorded RF in Hz for prediction and both spatial/timing
derivatives. No carrier-scaling or training-frame transfer defect was identified.
This is synthetic qualification, not a localization result or hardware calibration.

The new test follows the real research fast-scan exporter, TrackingInput loader,
scanner projection, position-window preparation and native branch packing. It
uses 101 visits, two receivers, channels 1/5, two different actual IF readbacks
within each channel, two LNB reference hypotheses and one/two/three native
alternatives. Nominal channel RF cannot satisfy the assertions. For identical
orbit geometry, both kernels independently satisfy rowwise RF homogeneity of
prediction and both Jacobians; visibility stays unchanged. A nonzero fitted-c
correction transferred from a low-band donor also agrees with the hand formula
using donor training centers, and with its re-expressed target native design.
There is no optimization, dataset access or reference/held evidence in this test.

Supporting production locations are `research_fast_scan_tracking.py:168`
(IF + LNB reference), `scanner_trajectory.py:97`,
`application/regional_position_inputs.py:60`,
`joint_association_sparse.py:23`, `hard60_score.py:103`,
`_regional_orbits.cpp:26–36`, `regional_position_score.py:91–111`, and
`channel_group_seeds.py:26–35`. Existing native/oracle comparisons and donor-center
tests remain useful; the new test adds independent semantic scaling assertions.
Positive RF validation alone cannot establish the physical correctness of a
recorded LNB reference hypothesis. The completed native-band control improved
frequency prediction while worsening DS21-039 position, so this audit supplies
no rationale for another calibration-flexibility sweep.

## Fixed native-cell prior

Seven isolated checks characterize the current rule without altering it. With
`A = 1 / 4.4 microseconds` and `fs = 2.5 MHz = 11 A`, the cell is
`floor(canonical_fs(CFO) / A + 0.5)`. The all-candidate prior gives each available
cell mass `1/B`, divided equally among its native proposals. The original native
input instead keeps one margin/rank/ID winner per cell. Neither slot order nor
cell label asserts emitter identity across windows.

For a close pair just below `A/2` and a remote candidate in cell 2, the close
pair receives total mass 1/2. Translating all measured CFOs and predictions by
the same tiny amount so the pair straddles `A/2` preserves every sampling-circle
residual, but changes its total mass to 2/3. At 1 Hz and 0.001 Hz scales, the
one-window NLL change follows the exact mixture floor and this mass ratio
(approximately `-log(4/3)`). An equally small translation away from a boundary
changes neither prior nor score. Whole-cell translations preserve the rule;
candidate-wise integer multiples of fs preserve cell labels and prior. A single
OFDM-period CFO offset is observable in the native likelihood, whereas an fs
offset is an exact sampling alias.

This discontinuity is a consequence of the declared zero-origin cell prior,
not evidence of an incorrect alias period or an implementation defect. The
synthetic example does not establish incidence or consequence on DS21. The
saved timing/calibration factorial's zero sampling-integer changes also rejects
integer switching as the dominant explanation for its four displacements.

The next gate is a separately frozen, bounded metadata incidence audit: inspect
only original training windows for native pairs with circular fs distance at
most the original 125 Hz sigma and different adjacent cells. Retain exact CFOs,
times, IDs, labels, boundary distances and counter blocks. Zero flagged pairs
falsifies this narrow close-pair boundary mechanism on the inspected inventory.
Presence alone does not justify exclusions, a prior change or new fits.

Saved factorial arrays omit measured CFO and native receive times and contain
the collapsed inventory. They cannot alone supply all passing alternatives.
The proposed audit therefore explicitly budgets frozen input loading, original
counter partitioning and scanner support projection, aligned to sealed training
metadata and saved collapsed candidate IDs. It does not call position preparation,
track reconstruction, ephemeris prediction, a likelihood or an optimizer.

Verification: seven boundary checks and eleven existing candidate checks passed;
the independent end-to-end RF test passed. Frozen scientific sources and persisted
contracts were unchanged. The incidence audit has not been run on DS21.
