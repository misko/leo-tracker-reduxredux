# Next: resolve competing location/timing solutions

Proposed follow-up; not executed in this report.

The DS7 middle-four 1 km probe is only 0.55 training nats worse, while its
local quadratic predicts 39.07. Before interpreting narrow curvature as
useful location information, test whether this alternative relaxes into a
separate joint location/timing optimum. Apply the same procedure to all
eighteen panels to avoid choosing only a favorable example.

1. Preserve the original q020 likelihood, masks, banks, scales, spatial bounds
   and timing bounds. Keep all tracks and the original result as a baseline.
2. For every panel, take both the lowest-loss 250 m probe and the lowest-loss
   1 km probe, choosing solely by training score. Start joint location/timing
   refinement from their audited positions and timings. Held outcomes and
   reference coordinates must not enter start or result selection.
3. Freeze optimizer limits and componentwise finite-difference audit gates
   before execution, test the new entry point and hash sources/inputs. Run
   one bounded child at a time with explicit timeout and memory receipts.
   Preserve failures and do not replace starts after seeing outcomes.
4. Compare qualified endpoints with the original point: training score,
   position separation, timing changes, held score, nominal reference error,
   and candidate-weight changes. Report all starts, not just the best one.
   This audits a finite set of alternatives and cannot certify global search.
5. If different solutions remain close in training score but geographically
   separated, retain the ambiguity explicitly. Do not collapse it to a local
   error ellipse. If a better training optimum emerges, evaluate its held and
   geographic performance across DS7/DS8/DS9 before promoting the search.

This follows the current profile evidence and complements the earlier
[correlated-contrast start ambiguity](../2026_09_29_correlated_contrast/README.md).
Those models differ; the prior result is not assumed to be the same mode.

If alternative optimization does not explain the inaccurate panels, the next
model work should investigate transferable residual structure across records,
distinguishing receiver/RF effects from uncertain satellite-associated effects.
Any orbit hierarchy must retain the earlier
[identity and calibration limitations](../2026_09_27_ds7_wave1/orbit-hierarchy/REPORT.md).
Cross-RX candidate agreement alone does not remove those limitations. Failed
cone, slope, drift and identity-coupling variants should not be repeated without
a new, testable mechanism. No new RF collection is proposed.
