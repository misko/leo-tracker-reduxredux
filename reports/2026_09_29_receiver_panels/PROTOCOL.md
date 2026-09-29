# Receiver-separated localization on consecutive panels

Use all 18 frozen consecutive four/eight-scan panels from
2026_09_29_consecutive_panels. Fit software RX0 and RX1 separately in each:
36 units, with three generic starts per unit. Preserve recording membership,
candidate banks, train/held masks, eligibility and the zero-decay shared-track-
scale likelihood. Split only by the existing software receiver_id metadata.
Require disjoint/exhaustive track partitions and nonempty receivers in every
recording. No outcome-based track or recording removal.

Use the same E/N starts (0,0), (3,-3), (-3,3) km, zero recording timings,
L-BFGS-B settings, bounds and qualification as the original panel model.
Select highest training likelihood among successful interior fits with
gradient infinity norm <=0.01. Preserve failed starts and abstentions.
No warm start, geographic selection, retries or receiver selection for deployment.

Audit the selected source-receiver training score, four E/N finite-difference
checks (1 m and 0.5 m, tolerance 0.002), exact track/count identities, and
geographic arithmetic. Evaluate held observations of BOTH receivers at the
source receiver's frozen position AND recording timings. Other-receiver
frequency offsets and candidate weights use its training data under the
unchanged profile; no target position/timing refit. Compare each receiver's
held score with the original both-receiver fit on identical tracks/counts.

Report every source fit's nominal geographic error, RX0/RX1 position separation
and timing differences, own/other-receiver held changes, all starts, and
median joint-panel errors/sub-km counts for each dataset/size/receiver. This
is an information-splitting diagnostic, not a calibrated beam or 20-degree
tilt model. Software-to-physical antenna mapping remains provisional.
No source-model choice based on the exposed unsurveyed reference.

Retain the original one-worker launcher, BLAS1/nice19, 12 GiB address-space
and 300-second process caps, >=14 GiB available memory before launch. No
overlap with another scientific worker. No new RF, waveform read, provider
fetch, propagation, public-contract change or golden-fixture change.
