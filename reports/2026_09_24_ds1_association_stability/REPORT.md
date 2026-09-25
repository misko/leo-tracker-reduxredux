# DS1 iteration-2: six-scan global-time association stability

The remaining 1.7–6 km post-seal error is not explained by a
Sacramento-versus-Reno association switch. The matched six-scan global-time
finalists are geographically much closer than the 0.390625 km final grid step,
use the same global timing value (-1.25 s), and have effectively the same
track-to-candidate maps.

| Six-scan group | Reno–Sacramento finalist separation | Post-seal error, Reno / Sacramento | Exact track-candidate matches | Common selected observations | Candidate-set Jaccard |
|---|---:|---:|---:|---:|---:|
| `20260921_00` | 0.116451 km | 6.048177 / 6.055479 km | 475 / 476 | 8,271 / 8,285 (99.831%) | 1.000 |
| `20260921_16` | 0.092262 km | 1.774903 / 1.688931 km | 298 / 298 | 9,686 / 9,686 (100%) | 1.000 |

For `20260921_00`, one 14-observation track changes candidate (`66257` to
`59797`); the two selected candidate *sets* remain identical (109 identities).
For `20260921_16`, every selected track-candidate mapping is identical. Thus
the approximately 6 km result and the approximately 1.7 km result both
persist when association identity is held almost perfectly constant under the
prior perturbation. The comparison supports an association-conditional source
of the residual, such as timing, propagation, geometry, or model error; it
does not identify which of those causes it.

The result artifacts preserve selected associations only at the winning point.
Their 121-row geographic traces preserve positions and RF objectives, but no
association maps for non-winning grid points. The nearby finalists above are
therefore the available direct test of grid-neighbour identity stability. They
are from independently seeded grids, so they are geographically nearby points,
not guaranteed nodes of one common lattice.

The `20260921_00` and `20260921_16` scan groups use different sessions and
share no track identities. Their different error levels cannot be attributed
to an identity change by comparing groups.

## Recommendation

Run a bounded association-frozen, RF-only profile at the already selected
global time of -1.25 s. For each six-scan group, use the common association
map (475 unanimous mappings for `20260921_00`, with the one divergent
14-observation track explicitly excluded or reconciled; all 298 mappings for
`20260921_16`). Score a 3×3 north/east grid centred on the paired-prior
consensus with one final 0.390625 km cell in each direction. Persist the
association map and RF objective at every point. That separates the local
geometric/timing profile from dynamic reassociation without an expansive run.
The reference coordinate must remain evaluation-only and cannot select the
centre, grid point, timing value, or association map.

## Provenance

This is a read-only comparison of the four sealed six-scan `global_time`
artifacts referenced in [diagnostic.json](diagnostic.json). It performs no
inference or selection. The reported errors were copied only from the existing
post-seal evaluator after its result-contract validation; they are descriptive,
not an input to any recommendation's selection rule.
