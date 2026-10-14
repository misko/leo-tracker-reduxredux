# DS21-039 qualified discovery coverage control

This training-only control applies the unchanged development coverage policy to
the genuine historical DS21-039 inputs. It tests whether allocating more of the
same 100-point budget to the initial grid changes the training-selected discovery
regions. It is not a localization accuracy result for any of Models A, B or C.

The implementation is `tools/ds21_039_discovery_coverage.py`, with component-owned
tests in `tests/tools/test_ds21_039_discovery_coverage.py`. Its `POLICY` is exactly
`ds21_discovery_coverage.POLICY`; it does not manufacture a generic initializer
protocol for the historical parent or modify any frozen scientific source.

## Authority and preparation

Source freeze is metadata-only. It validates the original
`reports/2026_10_13_ds21_039_root_cause/inputs-v1.json`, membership, census,
discovery protocol, all 100 historical point receipts, original hierarchy and
training selector. It verifies the full regional bank bytes and catalogue order,
and resolves the unique original TLE snapshot by its recorded digest and collection
time. No newer snapshot is selected and no orbit bank is rebuilt. The historical
bank has **836 satellites**, rather than the downstream 43-satellite candidate
subset used by the native association controls.

The historical discovery archived `ds21_common.py` and recorded its hash; its
live and archived bytes must still agree. The bound root-cause manifest also
records later numerical source archives and their then-current hashes. One helper,
`ds21_joint_proposals.py`, is explicitly recorded as differing from its historical
archive. Both recorded hashes and this declared difference are verified; the
adapter neither claims that helper was identical nor executes its archived code.
The old discovery did not retain a complete transitive source closure or modern
numbered slice receipts. Those attestations are not invented retroactively.
The new control freezes its own complete deterministic source closure and archives.
A metadata-only qualification of the real historical parent accepted the 836-bank,
100-point receipts and original snapshot; the current closure contains 406 sources.

The state machine is **source freeze → bounded training qualification → numbered
discovery slices → sealed training selector → optional evaluation**. Source freeze
does not prepare data. The separate qualification has a 60-second internal cap
(external TERM at 75 seconds, KILL at 80 seconds), including validation and final
source checks. A durable launch precedes preparation. It uses the original
training-only preparation port to bind missing counter-block assignments,
training time/RF frames, receiver/high-band fractions and clock nodes. Prepared
evidence hashes, original prior, partition seed/held-block labels, and saved
training frames must agree with the historical records. The completed termination
binds both the qualification and runtime protocol. Failed or orphan qualification
claims cannot be retried or accepted as cached success.

## Matched numerical scope

- Original DS21-039 all/low/high training observations, original 20-second causal
  counter-block partition and seed 20261012; no held preparation or projection.
- Original 250 km regional prior, full 836-satellite bank and candidate selection.
- Exactly 100 evaluated points, levels **[50, 25, 12.5] km**, priority view `all`.
  The original 50 km lattice supplies 80 initial centers, leaving 20 point slots
  for refinement. Grid alignment and radius inclusion are unchanged. This does
  not guarantee coverage by 25 km disks or a globally optimal discovery result.
- At every point, original three-view bootstrap and fixed-geography fitted-c
  calibration ports, candidate unions, priors, shared-clock layout and group
  offsets. Bootstrap cap 5 seconds; each view fit cap 5 seconds/200 iterations.
  Fitted c is retained throughout; no zero-c run, alternative seeds or retry.
- Each explicit numbered discovery slice has a 480-second internal cap including
  preparation/diagnostics/source checks, TERM at 495 seconds and KILL at 500 seconds.
  The inherited 31-second admission reserve remains in force.

Durable point launches, results and terminations use the original `AuditedPoints`
port. A clean checkpoint may continue in a new numbered slice with the same
100-point total budget. Failed slices, active orphan points, orphan slices and
changed authority refuse continuation. Returned nonstationary/failed numerical
outcomes remain visible under the original eligibility rules. Cached completed
reads validate authority and receipts without preparation or fitting. Source and
input validation occurs before and after numerical work.

Selection retains the original low/high/all own-objective ranking, then original
all-view score fallback, coordinate tie breaks and 12.5 km separation. The new
hierarchy is reconstructed from saved point scores to validate the terminal.
All three selected proposals remain training-selected; reference errors never
choose a point, seed, coefficient, hierarchy level or continuation.

## Evaluation and downstream limit

Freeze, qualification, discovery and selection use neither held data nor reference
coordinates. Optional evaluation is available only after a complete numbered
slice, all point receipts, original/new source authority, hierarchy and selector
have validated. It reports errors for the already selected three points and
cannot replace that selection. Historical failure receipts remain unchanged.

A downstream comparison would require separately qualified authority adapters
for the original shape → fresh bootstrap → hybrid → fixed-pool cold bootstrap →
ordered six-proposal exports, followed by the strict-first physical seed transfer,
receiver lifts and original 54-call A/B/C consumer. Existing generic consumers
reject this legacy-qualified policy. Those adapters and any downstream numerical
comparison are outside this control; no discovery-only outcome establishes a
sub-0.5 km result for the three original models.
