# Native adaptive pipeline adapter

This adapter turns native weighted-Hough tracks into the public
`leo_location_track` boundary and writes the research-private LOC1 replay
format.  It derives observation IDs, response-free support digests, partition
seeds, and training masks from the reconstructed tracks and explicit support
authority. Supplied tracker memberships can enter through the validated TSV
port; training masks are derived locally.

The LOC1 writer reads receiver sites and orbit states from an explicit
authority fixture, skips that fixture's complete track payload, and writes a
new payload from native tracks.  The CLI also writes `OUTPUT.loc1.tracks.tsv`
with the derived identities and masks for review.

Build with `./build.sh host`, `sanitize`, or `arm`.  The CLI is:

```
leo-adaptive-pipeline CANDIDATES.tsv GRAPH.tsv AUTHORITY.loc1 OUTPUT.loc1
```

To preserve a different tracker's supplied memberships, append
`--tracks TRACKS.tsv`. The research TSV reader checks source and lane identity,
measured CFO, alias conversion, support bounds and counts before deriving the
location records. It generates deterministic adapter identities for research
track labels; it does not rerun Hough or load server reference memberships.

`leo-adaptive-pipeline --validate-tracks CANDIDATES.tsv TRACKS.tsv` runs only that
boundary validator and reports the track and used-candidate counts as JSON.
Caller-provided orbit authority must cover the same acquisition epoch. This port
does not qualify a complete position estimate.

Append `--exclusive-candidates` to apply the optional
`exclusive-candidates-longest-v1` positioning policy. It prioritizes duration,
then point count, removes already claimed candidate IDs, splits at gaps over
four seconds, and retains fragments with at least eight points spanning four
seconds. Raw tracker output is preserved. `OUTPUT.loc1.members.tsv` records
original candidate IDs for auditing. Exact candidate exclusivity does not prove
that different candidates represent independent physical signals. Changing this
policy changes track identities and derived training partitions.
