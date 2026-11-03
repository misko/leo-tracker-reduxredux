# Whole-scan validation of curvature-fitted positions

For each of nine eight-scan panels, fit first four/predict last four, and
reverse: eighteen directed splits. Reuse the prior source-only baseline fit
selected by three-start training likelihood; verify its score on identical
source inputs. Fit shared curvature at the fixed 0.1 Hz/s² prior from that
baseline. Freeze source membership by the same training-only, same-RF,
cross-RX rules as shared_curvature. Target scans affect neither fit nor groups.

Compare both fitted positions under the SAME original full-track q020 target
likelihood, integrating each target's common timing offset uniformly over
[-5,+5] seconds. This tests location transfer under a common scoring model,
not the full posterior predictive density of the new curvature model. Do not
fit target positions/times or construct target curvature groups. Compare
paired geographic errors against the inherited exposed unsurveyed reference.

Retain previous fit qualification gates. Target scalar replay <1e-7; 16/32
nodes per timing-bank interval must agree within 0.01 log units. Refine only
failed integrals at 64/128 nodes under the same gate, preserving originals.
Report all failures, and no unqualified pair in aggregate success counts.
At most three concurrent workers, 180 seconds each. No RF or production edits.
