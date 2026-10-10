# Matched frame-convention fit sensitivity

Source-only preparation; no recording reconstruction or fitting. This is a physical-model sensitivity, not a proven receiver clock or orbit bug.

`PhaseObjective` preserves every SatelliteCorrection nuisance block, prior and lock. Relative timing uses Rz(+omega relative) at the same shifted ECEF bank queries; common timing remains a timestamp shift. Position and velocity secants remain distinct. Spatial derivatives use the ordinary observer-position Jacobian; horizon events are still nonsmooth and excluded from analytic gradients, as in production. Finite differences are tested away from horizon and interpolation-node events.

Two pure synthetic tests validate all spatial, common timing, relative timing, receiver clock, satellite offset/slope and static RF gradient blocks, and compare directly with the existing production SatelliteCorrection. At zero relative shifts, objective/common/spatial/nuisance gradients agree with control while relative gradients differ as physically expected: identical function values at one slice do not imply identical slopes perpendicular to it.

Proposed fixed12 matched experiment: same immutable126/117 members, ordinary bank/observations/priors and reconstructed B7 model. For each c arm start both conventions from the identical ordinary saved B7 vector and clock coefficients. Run one control and one phase fit with identical90 second soft budgets and600 iteration limits, using106's generic fitter and independent qualification. Preserve c=0 and fixed-RF locks. No cross-arm or cross-model warm starts, extra retries, winner selection or reference-guided starts. Failed/unqualified results remain explicit; original saved B7 endpoints and fresh control are separately reported.

Before each comparison require the ordinary original endpoint objective to reproduce the archive within1e-6; verify model layout and common physical priors. Compare raw/fallback qualification, score components, timing/clock coefficients, frequency residual effects and costs, then evaluate position only after both corresponding fits terminate. Alternative-model scores are model sensitivities, not an operational model choice. A better NLL is insufficient evidence for better localization or correct timing physics. Independent phase/timestamp provenance remains needed before deployment.

The numerical driver/controller and final immutable protocol are not yet built or frozen. Draft policy pins membership and existing fitter budget; no recording execution is authorized by this document.
