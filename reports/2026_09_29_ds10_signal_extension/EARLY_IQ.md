# Locating reproducible early I/Q changes

The three usable paired DS10-F010 visits were tested for changing information in
both I and Q over OFDM symbols 2–7 and all 28 common nonpilot carriers. The same
chronological discovery/evaluation split as the header assay gives 23, 9 and 11
evaluation frames for v1085, v1150 and v1162. These frames have been used for other
analyses; they are held out from the nuisance fits here, not a new confirmation
dataset.

Each receiver independently estimates a complex mean at each symbol/carrier
coordinate from discovery frames, and subtracts it from evaluation frames.
A separate discovery-only linear fit predicts Q from I at each coordinate.
All evaluation coordinates are retained: there is no confidence, activity or
agreement selection and no axis optimization. Thus percentages are not directly
comparable to the earlier confidence-selected raw-sign recovery scores.

| Visit | Centered I sign agreement | I covariance correlation | Centered Q agreement | Q correlation after I regression |
|---|---:|---:|---:|---:|
| v1085 | 62.6% | 0.395 | 50.0% | 0.035 |
| v1150 | 59.0% | 0.335 | 50.1% | 0.019 |
| v1162 | 63.0% | 0.328 | 52.3% | 0.001 |

The largest mismatched-frame Q correlations after regression are 0.040, 0.020,
and 0.049. No convincing extra quadrature sign stream is demonstrated by this
test. The I correlations greatly exceed the corresponding mismatch maxima
(0.030, 0.023, 0.023). Correlation centers each coordinate over evaluation frames
to remove static offsets; this does not fit sign thresholds or regressions on
evaluation data. Sign thresholds remain discovery-derived.

## Where the I variation is concentrated

As a further nuisance check, remove each evaluation frame's per-symbol common
carrier level and its projection onto the discovery mean's real carrier pattern.
The projection is fitted separately per receiver and frame, without using the
peer receiver. It removes a scalar template-gain fluctuation, but cannot exclude
frequency-selective channel error, interference, adjacent-carrier leakage or
other shared distortions. It may also remove genuine modulation.

Cross-receiver correlations after both removals:

| Symbol | v1085 | v1150 | v1162 |
|---|---:|---:|---:|
| 2 | 0.008 | −0.055 | −0.058 |
| 3 | 0.323 | 0.446 | 0.462 |
| 4 | **0.531** | **0.455** | **0.427** |
| 5 | 0.313 | 0.059 | 0.220 |
| 6 | **0.513** | **0.461** | **0.487** |
| 7 | 0.181 | 0.027 | 0.006 |

For symbol 4 the mismatch maxima are 0.074, 0.020 and 0.087; for symbol 6 they
are 0.117, 0.077 and 0.018. Their residual-sign agreements are respectively
77.3/71.0/68.2% and 72.0/71.4/69.2%. These signs describe departures from a
fitted mean, not established transmitter constellation bits.

This localizes reproducible early variation more precisely: symbols 3, 4 and 6
survive these nuisance checks in all three visits, whereas symbol 2 does not.
Symbols 4 and 6 warrant examination of amplitude levels and neighboring-carrier
leakage before assigning binary labels. The current evidence does not identify
QPSK, a new bit rate, satellite ID, timing, position, coding or a message layout.
All three visits share a conditional satellite candidate, which is insufficient
to attribute this behavior specifically to its identity.

## Artifacts and validation

`early_iq.py` saves per-coordinate soft values, discovery means, I-to-Q slopes,
the final detrended I arrays, evaluation frame indices and native carrier bins
under ignored `local/within-visit/early-iq/`. `summary.json` includes source cache,
source summary, script and output hashes, plus per-symbol and pooled comparisons.
All nonzero cyclic peer-frame shifts are descriptive controls; neither repeated
frames nor individual coordinates are independent trials. No significance tests
or decoded-bit-error claims are made.

Two synthetic tests confirm removal of a known linear leakage term and retention
of an independent quadrature component. Tests and lint pass. No new recordings,
manifest changes, commits or remote publication were performed.
