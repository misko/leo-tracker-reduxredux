# Completed checks

- **245 / 245** scan/configuration maps, each with matched c0/fitted-c arms.
- **490 / 490** saved endpoint objectives reconstructed exactly: maximum
  score difference **0**. This checks the stored endpoint, not a complete cold
  rerun of every discovery and optimizer path.
- **71 component-owned tests passed** across the input audit, fresh-discovery
  helpers, causal forecasting/correlations, Gaussian integration, frame links,
  geographic controls, linear transfer and sparse derivatives.
- All five nominal and previous element catalogues pass collection-time,
  element-epoch, byte/provenance and hash checks. Radio-only graph partition
  hashes are unchanged. Runtime input receipts contain no forbidden file reads.
- The current loader requires an isolated per-scan nominal catalogue with the
  complete original regional candidate set. It has no mixed-catalogue fallback.
  These records are byte-equivalent to the selected causal records used in the
  initial runs; endpoint replay verifies that the transport hardening leaves
  all numerical objectives unchanged. Original input receipts are preserved.
- **10 equivalent-control comparisons** (two controls × five scans) have
  exactly identical position parameters in both c arms.
- Changing four imported evaluation coordinate constants to Sydney leaves
  fresh S01 discovery bit-identical and changes **0 / 152** tested objective
  values. This is a targeted regression check, not a universal proof.
- **60** real-endpoint sparse-Jacobian checks agree with the original finite
  derivatives; maximum relative error **5.112 × 10⁻⁶**. Independent synthetic
  tests cover all six original methods and the robust residual transform.

The legacy nuisance profiles have **955 / 4,860** pixels across both arms that
reach the 48-iteration budget. They are marked with black dots. The surfaces
are finite-budget conditional profiles, not certified global minima. The saved
primary position fits did not report an iteration-budget stop. That does not
prove that every selected satellite identity is correct or that all nuisance
and position basins were discovered.

Three S05 endpoint inner solvers just exceed the declared precision tolerance
at 256 iterations. Both c arms of the two affected configurations were checked
with a common cap of 2,048 iterations at the frozen positions. All then satisfy
the tolerance. The largest objective change is **1.385 × 10⁻⁶** and the largest
conditional frequency-mean change is **0.0415 Hz**. Local quadratic estimates
of the effect on position are below **0.031 m**; these estimates are not new
position refits. See [the complete matched checks](precision_cap_check.json).

No new RF collection, held-out observations, following TLEs, pooled RF
calibration or ground-truth position initialization was used. The input
histories have complete regional candidate coverage but limited historical
depth because the service archive was not readable in this session.

The result remains an exploratory evaluation on DSX01 with settings developed
on DSX01. Loss surfaces condition on data-generated assignment branches. They
must not be described as exhaustive identity-marginalized likelihoods or
independent validation at a new geographic location.
