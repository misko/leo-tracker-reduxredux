# B common-clock relative-phase control

The next bounded experiment changes only satellite-relative timing physics in
the original B common-clock/free-group model. It retains the original Gaussian
mixture, fitted-c coefficient, clock precision, calibration, observations and
candidate sets. It runs the predetermined original worst cases DS21-039 and
DS21-023, with all/low/high views. These half views still share discovery.

Actual zero-fit qualifications completed in36.084s and25.269s respectively.
Both original saved objectives replay exactly. Native and Python phase
objectives/posteriors agree exactly; maximum gradient disagreement is
2.274e-13. At zero relative timing, the original and alternative objectives
and posteriors agree exactly, with shared-gradient discrepancy at most
9.095e-13. All-band full-vector finite differences cover70 and60 coordinates;
maximum absolute discrepancy is6.831e-5 and2.141e-4, within the predefined
absolute.003/relative.0005 tolerance. Original integer UTC alignment is
verified against freshly prepared training data. No held/reference data or
optimizer calls were used in qualification.

Each view now receives one original-physics continuation and one native-phase
continuation from its identical original stationary training winner, including
all nuisance values. The matched new search domain is a25km disk centered on
that winner. Six calls per case retain20-second/600-iteration limits; each
case has180-second whole-run/195-second TERM/200-second KILL limits.
This is a warm physical intervention, not a replacement six-start benchmark
or an end-to-end cost comparison. Both conditions have equal added budgets.
No old incumbent replaces a failed or nonstationary returned fit.

Each call receives exclusive launch/result/termination receipts. Independent
projected-gradient checks and exact objective replay gate accepted results.
Seal both cases before joining references. Report position changes separately
from likelihood, convergence and wall time. Qualification is correctness
evidence, not evidence that the alternative improves localization.

Implementation: tools/ds21_model_b_phase_control.py. Qualification receipts:
local/model-b-phase-qualification-039-v1 and
local/model-b-phase-qualification-023-v1. Both succeeded on their first launch.
