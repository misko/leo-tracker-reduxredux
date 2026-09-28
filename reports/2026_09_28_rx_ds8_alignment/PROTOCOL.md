# DS8 forecast-alignment diagnosis

This is a descriptive follow-up on the now-explored four-record DS8 confirmation
panel. It is not a new confirmation and will not tune geometry or predictor
parameters. Verify the complete preceding evidence index before reading its
dataset. Preserve the four evaluation recordings, eight lanes and all nominees.

For each eligible window and nominee, measure each receiver's nearest wrapped
candidate residual relative to the frozen prefix forecast. Retain empty candidate
sets explicitly. Report prior-weighted alignment within the existing 500 and
1,500 Hz thresholds, with empty or invisible observations contributing zero.
Normalize the original nominee log priors within each lane without a probability
floor. Candidate switching in nearest-residual diagnostics is not a physical track.

Partition paired alignment into both receivers, RX0 only, RX1 only and neither.
These are frequency-compatibility states, not satellite detections or beam entries.
Aggregate window means within recording and role, then weight recordings equally.
Also report fixed elapsed bins [0,30), [30,60), [60,90), [90,infinity) seconds from
each lane's first reception window, preserving missing-bin denominators. Do not
infer sample-rate causation from one recording per rate.

Freeze this protocol, implementation, tests, input and launcher hashes before the
real run. Bound the run to 120 seconds, one numerical thread and 4 GiB. No RF
collection, IQ analysis, external mutation, model fitting or candidate reranking.
Component tests and an independent numerical audit precede final interpretation.
