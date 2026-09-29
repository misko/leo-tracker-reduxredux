# Hard visibility consistency: proposed next test

This is a proposal, not an executed experiment or a change to the frozen
cone/trend sweep. Finish the four existing width arms before choosing a new
experiment. Do not select widths using exposed reference errors.

## Requirement

Every satellite explanation must use one continuous candidate trajectory,
one location, and the receiver's fixed axis and cone throughout a scan.
Keep location and receiver geometry shared throughout a consecutive scan
set. Different tracks may represent different satellites. Cross-receiver
identity sharing requires separately supported associations; timing order
alone does not establish an association.

The existing model shares these parameters but its sigmoid permits
outside-cone satellite explanations. Its reported hard-support fractions
measure this gap. A successful numerical audit does not close it.

## Two distinct outcomes to retain

1. **Complete satellite support:** every retained track has a candidate
   inside its receiver cone at every training observation. Report failed
   tracks and infeasible scans explicitly. Do not drop tracks or widen a
   cone to rescue a scan. This is support within the retained bank, not a
   full-catalogue impossibility claim or proof of correct associations.
2. **Satellite plus unexplained-track model:** outside-cone satellite
   hypotheses have exactly zero mass; unsupported tracks retain an explicit
   unassociated explanation. Report the satellite responsibility, counts of
   unsupported tracks, and complete-support status separately. Background
   assignments must not be described as a complete satellite explanation.

For a minimal comparison, replace the present sigmoid g_k with the indicator
that candidate k satisfies the whole-training-track cone. Retain q=0.20 and
the existing prior-mass routing:

    satellite k: (1-q) g_k / K
    background:  q + (1-q) (1 - mean(g))

K remains the retained training-horizon-visible candidate count. Preserve the
current explicit abstention for K=0. Do not renormalize surviving satellites
to conceal rejected mass. If all g_k=0 with K>0, the track has a background
explanation and no local frequency-based position force; it fails complete
satellite support.

## Numerical and predictive requirements before launch

A hard indicator makes the objective discontinuous at cone crossings. The
current smooth L-BFGS-B run and finite-difference gradient gates cannot be
copied and called a validated optimizer for that objective. First test a
bounded search strategy on synthetic problems with known boundary solutions,
including disconnected feasible regions and an infeasible scan. Freeze the
search budget, starts, training-only selection, and independent audit before
any geographic fit. A local stationary point away from a boundary is not
evidence that alternative support regions were searched.

Keep held observations out of training support and fit selection. Report
held geometric violations for each training-supported trajectory, alongside
held frequency prediction on identical observations. The existing conditional
frequency score does not enforce held visibility. Do not insert a held cone
factor into that score and call it a normalized predictive likelihood without
an explicit reception/non-reception model and a normalization test.

Use the same fixed eighteen panels and cached inputs for a matched comparison.
Keep the unsurveyed reference out of optimization and selection. Report all
planned panels, failed searches, infeasible scans, background assignments,
and the late DS9 eight-scan result. Preserve the distinction between assumed
nominal axes and calibrated receiver pose. Hard feasibility alone cannot
establish sub-km accuracy or travel direction.

The earlier fixed-position support audit already supplies a useful check:
at equal 20/30-degree half-angles no tested scan has complete training support;
at 50 degrees all 72 distinct scans do. Any new implementation must reproduce
those support outcomes at the original audit positions and timings before
attempting a refit. See ../2026_09_29_rx_cone_consistency/README.md.
