# Two independent synthetic cohorts for a regional publication challenge

Use the corrected 300 s native-candidate generator twice with independent
secret seeds. Each draw has four receiver locations in the existing
geographic boxes and a shuffled negative control. Cohort A keeps the
corrected generator's original observable model. Cohort B applies the
following private perturbations to a separately generated draw before
making its shuffled control.

- Each planted NORAD receives independent along-track time displacement
  from a zero-mean 0.9 s Gaussian clipped to ±3 s. Evaluate the emitter
  at that displaced, retarded epoch while the receiver remains at its
  physical reception time. Recompute the changes in range rate and
  frame delay. The prior independent four-region generator used the
  same phase scale and bound.
- Each active receiver/channel lane receives a zero-mean 75 Hz
  oscillator term with a four-second exponential correlation and
  ±225 Hz clipping. The existing robust Doppler likelihood used a
  four-second, 200 Hz correlated component. Choose the smaller amplitude
  for this moderate stress case.
- Add independent epoch readout jitter with 0.45 sample standard
  deviation and ±1.35 sample clipping at 10 MS/s. This is below the
  two-sample epoch agreement tolerance in the native GLRT comparisons.
  Independently in each receiver/pass lane, with probability one half,
  clear candidates across one uniformly placed 4–8 s interval. This
  is inside the 3–15 s gap range in the earlier holdout protocol.

The altered measurements retain the corrected native timestamp
representation and both radio ambiguities. The public causal
catalogue is the original archived snapshot in both cohorts and has
no injected orbit shifts. The challenged model and the reference
receiver get the same exact native packet and TLE for each trial.
The baseline and stress distributions are controlled simulation
conditions. They are broader technical checks on the exact-model
benchmarks and carry no claim to match the full measured RF domain.

For each site draw two tiles using an independent offer seed. The
correct 25 km square is centered 8–10 km from truth along a random
bearing. The omitted square uses an independent bearing and a center
45–115 km from truth. Each shuffled control receives its own draw's
first correct tile and has no defined geographic reference. Shuffle
opaque query IDs and execution order. Retain one present and one
omitted attempt per method and arm on each positive acquisition.

Freeze source, perturbation rules and all eight site slots before the
new seeds are drawn. Keep coordinate, transmitter and perturbation
labels out of receiver namespaces. Supply only the public
NativeCapture and its one offered tile. Allow two single-thread
workers on CPUs 8 and 9, each with a 100 s deadline. Seal
all predictions, retaining errors and timeouts, before scoring.
Score both calibration arms with matched inputs and budgets.
Report the two cohorts separately, including conditional RF fit,
wrong-tile publications, shuffled-control decisions and center error.
