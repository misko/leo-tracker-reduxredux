# DS9 complete recorded-scan native replay

This directory records a read-only replay of all 2,215 visits in
`scan-fw-3cfdaa6d75762cad`. The public `AdaptiveHopIqStore` verified every
compressed and decoded chunk against manifest
`sha256:5b8755586b9a84444ea3caf1bcb5cb0f6c6d80b7c9e3087666331608883de2bd`.
All 4,430 receiver windows had unique source timing and RF authority. Raw IQ
remained in `/srv/bulk/leo`; no raw corpus copy or storage mutation was made.

The production host detector produced 23,477 candidates, including 18,074
complete fractional evaluations. Native C3 retained 11,971 physical
observations. Native C4 used 3,110 of them in 64 tracks. The E2 adapter derived
fresh graph authority, observation identities, support digests, and training
masks, while reusing only receiver sites and orbit states from the LOC1
authority fixture. Its reader explicitly discards that fixture's saved track
payload. The resulting 64 tracks matched a catalogue satellite at both
registered scoring points, with scores 268.344678450005 Hz and
415.745326950356 Hz.

This executes the complete-recording E1/C3/C4/C6/C7 numerical path. It does not establish
scientific parity: the production fractional detector remains unqualified
against the server workflow. None of the 64 native tracklet identities equals
the server-derived identity because the candidate analysis digest changed;
that is not a physical missing/additional-track count. A physical membership
matching audit has not been run. The registered-point scores differ by
+44.509085199991 Hz and +4.316736564757 Hz. Both C7 searches exhausted their
400-point budgets, so their incumbents are not globally converged locations.

`report.json` binds the inputs, binaries, compact outputs, timings, stage
status, and descriptive comparison. `algorithm.json` binds the detector and
template hashes plus every visit's verified decoded-IQ digest. `native.jsonl`
is the detector transcript; `candidates.tsv`, `graph-candidates.tsv`, and
`tracks.tsv` are the C3/C4 handoff evidence; `native-e2.loc1` and
`location-score.json` are the location handoff and two-point score evidence.

The clean end-to-end host run took 82.09 seconds, including 41.40 seconds of
verified read/decompression/hash work, 25.92 seconds in detector subprocesses,
and 4.37 seconds in track construction. The harness enforces a 1,200-second
projected/runtime cutoff and stages at most 16 visits at a time.

The downstream C6 fixture and registered-point scores are reproduced with:

```sh
/tmp/leo-pipeline-host/leo-adaptive-pipeline \
  candidates.tsv graph-candidates.tsv \
  ../../tracking/native-e2.loc1 native-e2.loc1
/tmp/leo-location-final-host/leo-location score native-e2.loc1 2 \
  > location-score.json
```

The pipeline executable SHA-256 is
`0bb90ca973743acdd33a23aed8b464eb6c36f378cd9092f5eaae6b7b39fc084b`;
the location executable SHA-256 is
`cd6a7cb38bdc1e368fe4d06a5efb3e67b6cb8fa77ae8ea5e03634eec97137a35`.
The pipeline reads receiver sites and orbit states from the authority LOC1 and
discards its saved track payload.

C7 uses the two frozen priors without passing a saved winner or satellite
identity. Each command is bounded to five minutes and writes all 400 evaluated
points:

```sh
timeout --signal=TERM --kill-after=10s 300s \
  /tmp/leo-location-final-host/leo-location search native-e2.loc1 \
  38.5816 -121.4944 250 2 > c7-search/sacramento.json
timeout --signal=TERM --kill-after=10s 300s \
  /tmp/leo-location-final-host/leo-location search native-e2.loc1 \
  39.5296 -119.8138 500 2 > c7-search/reno.json
```

Both runs stop at the 400-point budget with `complete=false`. Their incumbents
are budget-limited results and are not globally converged locations.
