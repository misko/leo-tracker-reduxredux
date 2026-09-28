# Source-overlap diagnosis: `scan-fw-f147dd8a5bc99346`

This diagnosis used only the digest-verified cached public `TrackingInput`,
`prepare_adaptive_tle_position_inputs`, public trajectory reconstruction, and
`source_links.resolve`. It did not read pose coordinates, reception outcomes,
search results, or distance errors. No active search/helper file was changed.

## Finding

The endpoint failure is caused by exactly one public projected source anchor
appearing in two prepared tracks:

- candidate ID: `sha256:bcb85ff2bf3d9814090fd1726e8e125bc28e5c058766c5f3702c32a082099ec5`
- source location: visit 920, probe 0, RX1, rank 0, channel 2 lower edge
- support center: `1790480493731841956` ns
- observed track time/CFO: 124.851319638 s / -238398.4754616484 Hz

Accounting is otherwise clean: 62 tracks contain 2,771 track observations;
all 2,771 track observations resolve to exactly one source candidate. There are
2,770 unique source anchors and only this one collision. It is reserve in both
tracks. There are zero train/reserve collisions and zero train/train
collisions, so this does not leak a training observation into reserve scoring.

The affected tracks are:

| Track | Observations | Train/reserve | Time range (s) | Shared-anchor index | Occupied-second weight |
|---|---:|---:|---:|---:|---:|
| `sha256:03d7d08e26497262148d148aec95a4ef7f2ca0e0cb3274a526d5d0ecf8e0f832` | 15 | 9/6 | 118.054616648–124.971536326 | 13 | 7 |
| `sha256:2a89179ca751abd72738aa36b38b3cb4573646032b9b45e7391fae4f262b51cf` | 39 | 23/16 | 124.851319638–147.548535786 | 0 | 19 |

They are not identical or contained duplicate tracks. Their observation-ID
sets are disjoint, their lengths, masks, time arrays, and measurement arrays
differ, and the only shared source candidate is the boundary point above. The
public trajectory reconstruction itself places that same candidate in both
tracklets, which participate in different trajectory hypotheses. This is a
one-anchor branch/segmentation overlap, not two numerical copies of one track.

Excluding both collision-connected tracks would remove 2/62 tracks (3.23%),
54/2,771 track observations (1.95%; 53 unique anchors), and 26/1,424 occupied-
second track weight (1.83%) from this session.

## Handling assessment

Simply removing the endpoint guard or emitting the anchor twice is unsafe: it
would count the same physical reception evidence in two nominally independent
track contributions, while the Doppler endpoint is also repeated. Assigning
the anchor to the longer track would avoid the duplicate but would mutate one
public track's observation vector and its prediction bank; doing that only for
reception would also make the D and RX denominators inconsistent.

The literal frozen protocol makes missing/ambiguous anchors an error. Under
that rule this scan is terminally ineligible, is not replaced, and the
four-scan primary confirmation cannot be declared complete.

If the experiment owner amends the input-integrity policy before any distance
unblinding, the simplest coherent salvage is a cohort-wide, outcome-blind
collision-component rule: for every frozen session, construct the bipartite
track/source-anchor graph and exclude every whole track in a component where a
source anchor has degree greater than one. Apply the same retained track set to
prediction banks, robust D scoring, reception scoring, and occupied-second
weights; then rerun every confirmation scan under one new code hash. This
preserves intact public tracks and prevents both Doppler and RX double
counting. It must be reported as a protocol amendment and sensitivity, not as
the original primary result. The current scan-0 output, if it completes, cannot
be mixed with amended-run outputs.

Whole-track exclusion is scientifically safer than choosing the longer branch:
duration/support selection would retain more observations but creates a new
branch-ownership rule not used by the frozen frequency calibration and may
prefer one genuine trajectory hypothesis. Excluding both is conservative and
depends only on source provenance topology, not signal strength, satellite
fit, reception, position, or search outcome.
