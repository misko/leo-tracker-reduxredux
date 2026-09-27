# DS6 — roof recordings with location and receiver direction

DS6 freezes the **exact 43 recordings approved in the preceding inventory**:
95,269 visits on `radio_pluto_5d4d`, with both software receivers (0 and 1).
Capture starts span September 26, 2026 at 23:30:17 UTC through September 27
at 05:39:43 UTC; the final capture ends at 05:44:45 UTC. The inventory was
observed beginning at 05:55:58 UTC. Newer recordings are not added implicitly.

Membership includes completed, published recordings with qualified timing,
attested source spans and verified immutable pose attachments. Analysis
readiness is not an admission criterion. The approved inventory records 37
GLRT products ready and 32 completed tracking products; these are historical
observations, not guarantees about current processing status.

## Location and direction

The attached authority is `gauss-r20-roof-20260926-v1`: operator-supplied
coordinates **37.849056280893684, -122.48575489722863**, interpreted as WGS84.
Physical RX1 points west (270 degrees); physical RX2 points east (90 degrees).
The mapping to software RX0/RX1 is provisional. Altitude, actual elevation,
and directed RF phase-center baseline remain unknown. Nominal fixture mount
separation is 80 mm with 10-degree outward tilt; this is not a calibrated RF
baseline. The dataset carries location metadata and must not be described as
blind to receiver location or as surveyed GPS ground truth.

## Frozen products

- `manifest.json`: ordered membership, exact source/pose hashes, nanosecond
  capture times, finalization times, and recording properties.
- `approved-inventory.json`: the unchanged proposal approved by the user.
- `pose-authority.json` and `pose/`: the authority and all 43 pose attachments.
- `recordings.csv` and `TABLE.md`: reviewed recording inventory.
- `evaluation-units.json`: full dataset, 43 whole-session units, sample-rate
  subsets, five consecutive groups of eight, and a three-session remainder.
- `SHA256SUMS`: byte-level seals for every other artifact in this directory.

Rate counts are 15 at 2.5 MS/s, 9 at 5 MS/s, 5 at 7.5 MS/s, and 14 at 10 MS/s.
All receivers, visits and tracks from a session stay together during evaluation.
Groups of eight preserve chronology; the last three sessions are explicitly a
remainder. Evaluation units are not a train/test split. Scientific validation
must choose and record randomized whole-group holdouts before fitting, and
must explicitly declare whether location/direction metadata is used as a prior.

This is a metadata-only freeze: original IQ is referenced through its capture
identifier and manifest digest and remains untouched. No new RF was collected.
Source manifests and pose bindings were revalidated during minting; raw IQ
payloads were not decompressed or rehashed. Verify the local artifact seals with
`sha256sum -c SHA256SUMS` from this directory.
