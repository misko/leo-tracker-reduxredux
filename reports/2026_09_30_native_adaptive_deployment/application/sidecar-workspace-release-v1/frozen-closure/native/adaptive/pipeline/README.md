# Native adaptive pipeline adapter

This adapter turns native weighted-Hough tracks into the public
`leo_location_track` boundary and writes the research-private LOC1 replay
format.  It derives observation IDs, response-free support digests, partition
seeds, and training masks from the reconstructed tracks and explicit support
authority.  It does not accept saved memberships or masks.

The LOC1 writer reads receiver sites and orbit states from an explicit
authority fixture, skips that fixture's complete track payload, and writes a
new payload from native tracks.  The CLI also writes `OUTPUT.loc1.tracks.tsv`
with the derived identities and masks for review.

Build with `./build.sh host`, `sanitize`, or `arm`.  The CLI is:

```
leo-adaptive-pipeline CANDIDATES.tsv GRAPH.tsv AUTHORITY.loc1 OUTPUT.loc1
```
