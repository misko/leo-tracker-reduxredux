# Native in-memory positioning composition

`native/adaptive/pipeline/in_memory_cli.cpp` connects public component ports:
checkpoint readers → exclusive track selection → measured location tracks →
native TLE propagation → borrowed-input location session → JSON output.
It writes no orbit-state or LOC1 intermediate files. Parsing objects are
released before search; orbit and track owners remain alive through the search.
The previous CLI adapters reuse the same readers and JSON writer. No CLI
implementation is imported by another component or by the location analyzer.

Build with `native/adaptive/pipeline/build.sh MODE OUTPUT LOCATION_LIBRARY_DIR`.
The optional third argument enables `leo-memory-position`. Invocation:

```
leo-memory-position OBSERVATIONS GRAPH TRACKS TLES KNOT_START_S KNOT_STEP_S KNOT_COUNT LATITUDE LONGITUDE RADIUS_KM WORKERS ASSOCIATIONS.json
```

The capture epoch comes from graph authority. Catalogue eligibility remains
explicit in the supplied counted TLE checkpoint. The adapter uses the existing
exclusive-candidate policy and validates execution geometry. Association output
is exclusively created; only successful completion emits the search result.

Host full-catalogue comparison passes: ordered search coordinates and selected
site are exact, maximum score difference is 3.990408e-11 Hz (tolerance 1e-9 Hz),
and all final identities, tau values and association values are exact. This
host composition propagates states itself, while the preceding fixture used
ARM-propagated states; it does not claim whole-search bit identity on host.

Pipeline unit tests exercise the shared observation/support readers, including
invalid numeric fields and duplicate IDs. Orbit CLI tests preserve the existing
rejection cases and exact LOC1/raw-state packaging. The memory CLI's geometry
and missing-input rejection checks pass. Build logs and source/payload snapshots
are retained here. Physical full-chain evidence is in
`../fullchain-memory-overlap-v1/`.
