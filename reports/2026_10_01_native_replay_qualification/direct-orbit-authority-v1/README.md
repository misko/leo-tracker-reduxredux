# Direct native orbit authority packaging

`leo-orbit` now accepts an explicit optional output mode:

```
leo-orbit TLES START_UTC_NS KNOT_START_S KNOT_STEP_S KNOT_COUNT OUTPUT.loc1 --loc1-site X_KM Y_KM Z_KM UP_X UP_Y UP_Z
```

It generates native states from the supplied TLE catalogue and writes the
existing LOC1 layout with zero tracks and one caller-supplied site. The pipeline
adapter then inserts measured track data. Default raw-state output and stdout
metadata remain unchanged. This removes host-side state packaging from the
planned full-chain replay. Catalogue order is taken from the generated snapshot.

Component checks verify exact raw-state/LOC1-state bytes, header, catalogue ID,
site fields, and rejection of nonfinite sites or non-unit up vectors. The 12
previous rejection cases still pass. Full-catalogue host propagation matches
the preceding host state bytes exactly; the track/support and membership
evidence produced by the existing converter is unchanged.

This fixture carries one explicitly supplied site rather than the earlier
two-site diagnostic authority. Regional search uses its explicit latitude,
longitude and radius; it does not take a reference location from these sites.
The full LOC1 file consequently differs in site count/header. Do not claim
whole-file identity to the two-site fixture.

Physical ARM generation and direct LOC1 packaging completed in 5.406884 wall /
5.334982 CPU seconds (58,828 KiB peak RSS). All generated state bytes equal the
previous qualified ARM propagation. The existing native pipeline then consumed
this new authority plus the lossless queue16 observation/support checkpoints
and qualified tracks, taking 3.746342 wall / 3.428735 CPU seconds (46,684 KiB).
The resulting LOC1 equals the previous input exactly after the declared removal
of the second diagnostic site; all track/support and membership evidence is
unchanged. See `arm-comparison.json` and `conversion-comparison.json`.

This establishes the direct TLE→authority→measured-track input connection on
ARM without a host packaging step. Catalogue eligibility remains supplied by
the caller. It does not qualify concurrent full-chain cadence by itself.
