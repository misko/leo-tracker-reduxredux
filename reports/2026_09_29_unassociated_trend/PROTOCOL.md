# Conditional-bank unassociated-trend experiment

Freeze before any geographic fit. Use all 18 consecutive four/eight panels and
the three generic starts in the completed frequency-contrast study. Two arms:
q000 has background prior probability 0; q020 has background probability 0.20.
Both use signal Student-t4 scale 100 Hz and the same conditional visible-bank
normalization. Do not select an arm or tune constants from geographic outcomes.

Signal prior mass is uniform over the retained candidates passing the original
training horizon gate at the evaluated position/timing. Require at least one
visible candidate per track; otherwise the model explicitly abstains, in both
arms. Held evaluation uses the same training-derived visible set. This defines
a normalized frequency density conditional on the retained visible bank, not a
full-catalogue or detection model. The bank was selected using data. Omitted
satellites are not recovered, and responsibilities are not calibrated physical
satellite/clutter probabilities. All derivative stencils must preserve the
visible set. A changing visibility count can change the objective globally;
do not assume the normalization is a globally constant shift from the old model.

Background frequency is an unknown constant plus a zero-mean linear slope and
noise. Marginalize the slope and shared inverse-gamma scale, eliminate the
constant with the same training-anchor contrasts, and use Student-t4 scale
D [100^2 I + 2000^2 t t^T] D^T. The 2000 Hz/s slope scale and 20% branch prior
are declared broad prototype assumptions, not measured calibration or tuned
estimates. No free held slope, per-track trimming, polynomial selection or
reference-informed prior is allowed. Conditional held log density is the full
mixture density minus its training marginal, on identical contrast coordinates.

Training signal responsibility multiplies each track's geographic derivative.
Report its sum, quantiles and number above 0.5 for every panel, along with the
position and held outcomes. Those are descriptive diagnostics, not confidence or
an identifiability proof; a numerically converged background-dominated fit may
still have an uninformative position. Unit-background synthetic checks must show
zero geographic force. Empty visible banks are abstentions, never silently
assigned unit background probability. No receiver cone or timing split is added.

Before freezing require all eight prototype tests: exact rational matrix
densities/all anchors/translations, density and conditional-mixture normalization,
zero-background control replay, unit-background zero force, attenuation of an
unsupported synthetic track, all position/timing derivatives, held isolation
after rebuilding cached background quantities, and empty-bank abstention.
The initial ill-conditioned SciPy matrix comparison differed by 5.55e-8; exact
rational matrix elimination verifies the implemented density to 11 decimals.
Moderately conditioned cases additionally agree with SciPy. No geographic run
was performed before these checks passed.

Fit shared E/N and one timing per recording. Starts E/N (0,0), (3,-3), (-3,3) km,
all timings zero. Bounds E/N +/-12 km, timing +/-5 s. L-BFGS-B maxiter 140,
maxfun 200, ftol 1e-14, gtol 1e-8, maxls 30. Select the greatest training score
among successful fits with gradient infinity norm <=0.01 and all parameters
at least 0.001 from bounds. Do not use held scores or reference errors. Never
retry completed fits or substitute another start after a selected audit fails.

Replay training score within 1e-7. Check all derivatives using E/N steps
0.001/0.0005 km and timing steps 62.5/31.25 microseconds. Each discrepancy
must be <0.002; timing stencils must not cross quarter-second interpolation
nodes, and their numerical derivatives must agree within 0.002. Preserve all
failures. Require all three block audits for each dataset/size median. Compare
q020 against q000 on identical held observations and report the prior contrast
baseline separately. Training scores across the old full-catalogue normalization
and the new conditional-bank model are not directly comparable.

For q000, independently replay the old contrast model at each selected position.
Require the exact visible-count training-score correction, identical geographic
gradient and held predictions to numerical tolerance. This pointwise check is
not global equivalence of the optimization objectives.

One worker, BLAS1/nice19, 4 GiB address-space limit, 180 s per child process and
MemAvailable >=5 GiB before launch. Record commands, exits, resource receipts and
hashes for all jobs. Administrative admission failure stops execution. No raw
waveforms, new RF, candidate rebuilds, propagation or provider requests. These
dependent single-site panels use an exposed unsurveyed reference; errors do not
establish surveyed accuracy, blind generalization or calibrated resolution.
