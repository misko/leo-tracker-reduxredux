# Phase recovery prototypes

User requested SOL delegation, implementation and tests. This run uses existing recording artifacts and explicitly synthetic known-truth signals. No new collection or hardware change is included.

Three independent SOL workstreams own reference calibration, reversible tracking, and observability validation. Root reviews the distinction between phase-coordinate restoration and physical recovery, checks tests, and assembles results.

Required outcomes:

- Independent-reference estimator that cannot learn away target geometry, with known injection-path phase retained in the calibration equation.
- Reversible tracking that preserves the removed correction and reconstructs its input phase, while retaining ambiguous cycles and gaps.
- Positive synthetic recovery cases and negative controls for absent references, unknown path phase, receiver drift and non-common propagation.
- Existing-data demonstration labeled as measured combined phase unless independent instrumental authority is actually present.

Frozen real-data scope is the same five dwells259–263 and 445 cached pilot frames. Simulated geometries, instrument states and reference errors must be persisted with deterministic seeds. A successful reconstruction identity is not a recovered geometric phase. Multiplying a frame phasor by a center-time correction cannot reconstruct the raw IQ average before frequency derotation.
