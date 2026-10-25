# Receiver-specific graph CFO noise control

Separating the RX1 and RX2 frequency-noise laws improves the conditional held-family contrast score in all 24 DS24 cases. The median total gain per scan is 429.55 negative-twice-log-density units. This qualifies the frozen noise model for position propagation; it does not establish a position improvement or that the estimated variance is pure hardware noise.

## Construction and validation

The original graph, polynomial degrees, aliases, point membership and nominated satellite family labels are fixed inputs. Curved pieces with sufficient residual degrees of freedom contribute polynomial projection residuals. Training uses squared residuals divided by one minus leverage, matching the original noise estimator. The compared laws are a pooled constant-or-margin variance model and two separate receiver constant-or-margin models, each retaining the original 40–600 Hz sigma bounds and training-only BIC choice between constant variance and `floor + strength / fractional_margin`.

Three folds randomly assign whole nominated satellite families across both receivers and all channels. Unmatched tracks form whole-track groups. Seed 20261025 is combined with each scan suffix using `SeedSequence`; all assignments are persisted. Every held group is scored once and no observation appears in both training and validation. Variance-law fitting and constant-versus-margin selection use training pieces only. Polynomial degree, piece membership and the original nomination labels remain inherited from all-data graph selection, so this is conditional proxy validation, not an untouched end-to-end association test. Held contrast projections use fixed polynomial degrees and the held pieces' timestamps.

For a held piece with polynomial-orthogonal columns Q, the scored vector is Qᵀy with full covariance Qᵀdiag(variance)Q. Both the quadratic term and log determinant are retained. The leveraged point residuals are training samples, not falsely independent held-out observations. Pieces do not share observation IDs; the implementation raises an error if they do. Residual correlations across different pieces or families are not modeled by this noise proxy experiment. Family grouping addresses shared identity leakage but does not establish transfer across observation sessions.

The qualification rule was frozen before geographic evaluation: total held-group density gain above 2 log 2 and positive gain in at least two of three folds. All 24 cases pass. Each qualifying case then refits the two receiver laws on its original complete graph and generates per-observation sigmas. No geographic truth, fitted position or orbit prediction enters variance estimation; inherited family labels are used only to group folds.

## Position adapter and interpretation

The adapter clones the original scan, leaving persisted contracts unchanged, and supplies the same per-ID sigmas to curved and predictive observations. The time-only whitening and gate semantics, all physical priors, labels, masks, aliases, weights and search budgets remain unchanged. An explicit in-memory selector activates the existing nonconstant-noise branch; its positive BIC field is a selector, **not a new measured BIC gain**. Both c=0 and fitted-c arms are reconstructed and checked for exact sigma-map parity.

Position adoption requires the original gates in both c arms; otherwise the exact saved baseline pair is retained. Geographic evaluation is separate and does not select models, receiver scales, cases or gates. See the parent report for trial and policy position outcomes, including every fallback.

Three component-owned tests verify exact constant-noise contrast density, invariance to polynomial offsets, and complete disjoint grouped folds with bounded noise across all 24 cases. Independent model review and endpoint replay audits accompany the results. No raw IQ, new recordings, satellite reassignment, graph recovery, or component production code was changed.

Artifacts: `protocol.json`, `summary.json`, `results/DS24-*.json`, `noise_controls.py`, `adapter.py`, `position_protocol.json`, and `test_noise_controls.py`. Frozen input paths and SHA256 bindings are in the position manifest. The exact dataset/model provenance and reporting-only geographic reference are in the parent report.
