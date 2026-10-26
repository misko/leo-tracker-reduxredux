# Independent audit

The frozen prototype and recorded inventory pass their source, coordinate,
ownership and terminal audits. Passing these audits establishes faithful
execution of the declared engineering tests; it does not qualify a source,
satellite association or position estimate.

[The prototype terminal receipt](prototype_terminal.json) checks all 24
lane/method slots, original maximum-margin winners, complete candidate
membership, one candidate per receiver window per path, exclusive candidate
ownership across paths, shared-window counts, circular CFO/epoch lifts and the
saved graph memberships. An independent reconstruction of every selected
path's objective differs by at most 4.27e-14. No selector, detector or graph
was rerun by the audit.

The prototype retains 40 path hypotheses across the controls and methods.
Its 38 graph tracks comprise 16 literal `insufficient_support` and 22
`structure_flagged` statuses. Structure flags take precedence over the support
status in the unchanged diagnostic. Every track has fewer than 20 points;
none is quality qualified. Correlated hypotheses from a shared window cannot
be added as independent observations.

CFO-only and epoch+CFO select the same candidate paths in all eight lanes of
the original synthetic panel. The added epoch term therefore demonstrates no
incremental selection benefit here. The separated-epoch toy's improved known
source-proximity coverage is a result on exposed development fixtures. It
does not validate the inferred number of physical sources. Coincident-epoch
candidate paths still mix proximity to both injected sources.

[The recorded terminal receipt](recorded_terminal.json) independently checks
all 60,391 exported candidate rows, 13,484 receiver windows, 3,754 exact native
winner joins and all 117 original owner ID sets. The 5,206 gated deduplicated
hypotheses include 501 nearby alternatives in 483 windows. All 117 owners
complete the frozen persistence rule, and zero pass. The positive port is
empty with no replacement; the first of three eligible unflagged controls is
RX2 CH5 T003. This stops the recorded positive follow-on under this rule. It
does not establish absence of coherent signals outside the nearby-alternative
class or outside these engineering limits.

Frame phase is reconstructed from native integer counters and the fractional
local epoch modulo exact fs/750. Historical opaque observation IDs remain
distinct from research receiver-window IDs. Missing recorded acquisition CFO
stays null. [The descriptive gap readback](grid_readback.json) also passes:
only 0, 6 and 30 of 501 pairs lie within 1, 5 and 25 Hz of a nonzero refinement
bin multiple. Gaps nevertheless cluster near the 250 Hz deduplication floor;
neither that shape nor continuity proves distinct emitters.

[The separate single-source response audit](single_source_terminal.json)
checks 24 complete paired calls, 48 receiver outputs and 384 exported
hypotheses under the exact historical detector implementation/environment.
The fixed one-source metadata, seeds, distinct IQ/noise hashes, zero clipping
and 31.753-second cumulative budget agree. The waveform is the deployed
sampled-template inverse-model control, not independently established
transmitted-waveform authority.

[The unchanged-selector application audit](single_application_terminal.json)
passes all six slots. CFO-only and epoch+CFO each produce a 24-point main
path plus a 14-point secondary path on RX0, and 24 plus 16 points on RX1.
All 24 windows remain the union coverage: the secondary paths reuse 14 or
16 correlated receiver windows. The main tracks are `structure_flagged` and
the secondary tracks are `insufficient_support`; none is quality qualified.
A second coherent path is therefore possible with one injected emitter.
This is a specificity warning for the engineering hypothesis extractor,
not demonstrated false operational admission or a calibrated false-source
rate. [The strategic critique](NEXT_DIRECTIONS.md) describes the next useful
measurement and independent-owner questions.

Two audit-reader errors were repaired without changing scientific artifacts:
the grid seal uses a nested absolute-path file map, and original-winner nodes
obtain their window IDs from the frozen candidate/window map. Both failed
attempts are preserved. The unrelated repository diff remains unchanged.
