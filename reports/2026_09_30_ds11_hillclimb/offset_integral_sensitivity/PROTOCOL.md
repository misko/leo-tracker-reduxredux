# Within-track CFO-integral sensitivity

Reuse exactly the24 track cases from the prior integral feasibility audit.
At each frozen original IID endpoint compare the two highest-profile-score
visible candidates under scalar CFO integration. Do not search other candidates
or infer full-catalogue association validation from this two-candidate check.

For the original leading candidate, evaluate the integral at +/-100m EN
perturbations. Track constants cancel when comparing its correction to the
profiled score within the same track. Also compute the exact posterior-expected
score derivative via independent vector quadrature and compare it with scalar
integral finite differences at1e-4km and1e-5seconds. Prediction derivatives use
the same centered steps; all times remain interior to the bank.

Require24 completed cases, scalar/vector log-value agreement<1e-6,
gradient discrepancy<1e-3 per optimizer coordinate and no quadrature failures.
Report correction variation and leading/runner-up gap changes without reference
error or held samples. Numerical feasibility is not a positioning gate.
One worker, one numerical thread,90second cap, no IQ/orbit updates or fits.
