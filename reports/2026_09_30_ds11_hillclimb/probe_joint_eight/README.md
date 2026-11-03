# Eight-frame pooling helps, but joint refinement fails its advancement gate

All six comparisons complete using eight frames and independent frame/carrier
gains. Joint frequency refinement beats cached acquisition frequencies on5/6
probes, with positive mean and median held-NMSE gains. It beats separate
refinement on only2/6 and worsens both aggregate comparisons against separate.
The stronger prospective advancement gate therefore fails. No frequencies are
propagated into positioning and no broader joint-refinement campaign follows.

| Pair | Cached held NMSE | Separate-frequency held NMSE | Joint-frequency held NMSE |
|---|---:|---:|---:|
|0|0.935143|0.932466|0.932713|
|1|0.906369|0.904839|0.904973|
|2|0.915430|0.915130|0.915142|
|3|0.937660|0.937434|0.937412|
|4|0.943877|0.944185|0.945017|
|5|0.951843|0.950572|0.950426|

| Comparison | Wins /6 | Mean paired NMSE gain | Median paired gain |
|---|---:|---:|---:|
|Joint versus cached|5|+0.000773|+0.000842|
|Joint versus separate|2|-0.000176|-0.000073|
|Separate versus cached|5|+0.000949|+0.000786|

Positive gain means lower total held squared error normalized by total held
energy. These are waveform-prediction gains, not position improvements or
calibrated frequency errors. All three arms reconstruct both pilot contributions
on identical samples; only frequency selection differs. Candidate frequencies
are shared across frames while complex gains remain independent. No coherent
phase continuity between frames is assumed.

Every case supplies all eight frames with sufficient common training and held
support. Twelve joint starts qualify; separate fits are interior. Selections
use fitting samples and are saved before held evaluation. Per-frame held scores
are retained, and frame0's cached result exactly replays the preceding
single-frame experiment. The previously negative cases remain in the denominator.

The single worker exits0 in4.61seconds under its120second cap. Two component
tests cover eight-frame frequency recovery with changing complex gains,
analytic derivatives and energy-weighted aggregation. Independent QR solves
reproduce all144 frame scores and18 pooled scores to3.34e-16 while verifying
source hashes, excerpts, masks, selections and all12 qualified starts.
No new IQ collection, archive reads, orbit update or position fit occurs.

Evidence: [protocol](PROTOCOL.md), [outcome](outcome.json),
[independent verification](verification.json). Plan SHA256:
`aca560326a48b4ea70822f1765a25e49f2fcb430c2c9f170527e05f964cb5791`.

This result supports using multiple frames in this small waveform comparison;
it does not establish that joint frequency fitting is worth its extra model
complexity. The earlier two-scan long-pilot position experiment already failed
directional replication. Small waveform gains must not be promoted as a new
geographic result, and neither fitting bounds nor acceptance thresholds are
retuned after this test.
