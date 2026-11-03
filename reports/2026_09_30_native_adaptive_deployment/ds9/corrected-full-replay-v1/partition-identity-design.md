# Partition identity design audit

This is a source and evidence audit. It changes no public contract, runtime,
golden, identity, or location result.

## Current v1 binding

The native and reference implementations use the same v1 identity shape. A
source group binds the recording digest, visit, receiver, and probe. A candidate
then binds that source group, candidate rank, and the analysis artifact digest:

```text
source_group_id = H({capture, probe, rx, visit})
candidate_id    = H({analysis, group, rank})
```

Tracking derives segment and tracklet identities from the ordered candidate
identities. The location pipeline derives each observation identity from the
candidate ID, tracklet ID, and relative alias. Its response-free support digest
then hashes the observation identities, exact support times, and all four
factorial-moment lexemes. The split seed is:

```text
H({policy: "persistent-hop-fixed-orbit-randomized-residual-v1",
   response_free_support_digest: support_digest,
   selection_protocol_digest: protocol_digest})
```

Each observation is ranked by hashing its observation ID, the
`deterministic-randomized-observation-v1` policy name, and that split seed. The
lowest `floor(0.6*n)`, bounded to `[2,n-1]`, form the training set.

The relevant native sources and frozen reference sources are bound below:

| Source | SHA-256 |
| --- | --- |
| `native/adaptive/runtime/projection.cpp` | `b1a367dea74f682dd6ffec8fae7a07f503db568ebc73ab914d7d1a1233651727` |
| `native/adaptive/tracking/tracking.cpp` | `f2fb20b646287e4ef0392131a48e3dff337b14db69ef09564eae1b0439b659bc` |
| `native/adaptive/pipeline/pipeline.cpp` | `c3b891215c2f4585d4a09d3c35d6b14e9cf6c15ff1bcab7ae6ddc857f3e1e8c1` |
| frozen `leo/application/scanner_trajectory.py` | `844f23c068af8c6f6a0477f1a0ce2997e1066b2585d4cbca24781f62ab8c3e7b` |
| frozen `leo/operations/adaptive_tle_position_inputs.py` | `2b2c68c2eab3bd26d60c9d366fa6b1dc8cc580b3b7b77ca549f8cf2383fdd477` |

The standard analysis digest is a content provenance claim about the actual
analysis artifact and configuration. The fresh native analysis is numerically
conformant within the declared tolerances, but its artifact descriptor and some
numeric lexemes are different. Substituting the reference analysis digest would
therefore make a false byte-provenance claim. The separate native analysis
digest is correct under v1.

## Measured sensitivity boundary

With the opt-in server support profile, 8 of 11,747 moment2 lexemes and 32 of
11,747 moment3 lexemes differ from the reference; their union is 32 rows. Nine
of those rows are selected by the 64 reference track memberships, affecting
nine tracks. This count pairs candidates by the already-verified physical row
ordering and then inspects the reference track candidate memberships.

Even under a hypothetical common candidate and track provenance, those nine
tracks serialize different support material. V1 consequently hashes different
support and seed inputs, and recomputes their observation rankings. A changed
seed does not by itself prove that the final training mask changes, so this
audit does not assign every location-score difference to the partition. The
observed fresh-native run changes all 64 provenance-bound seeds and changes
1,602 of 3,372 mask bits; that is direct sensitivity evidence, not a controlled
causal decomposition.

## Principled compatibility design

Preserve all v1 identities. If cross-implementation partition stability is a
product requirement, introduce an explicit v2 partition policy based on
physical support while retaining artifact provenance separately:

```text
physical_observation_key = H({
  schema: "org.leo.physical-support-observation/v1",
  source_group_id,
  relative_alias_index,
  support_start_utc_ns,
  support_center_utc_ns,
  support_end_utc_ns
})

physical_track_support_digest = H({
  schema: "org.leo.physical-track-support/v1",
  lane: {receiver, channel, edge, actual_rf_hz},
  observations: sorted physical_observation_keys,
  tracking_semantic_profile_digest
})

split_seed = H({
  policy: "physical-support-randomized-residual-v2",
  physical_track_support_digest,
  selection_protocol_digest
})
```

V2 ranks the physical observation keys with the new seed. It excludes analysis
artifact IDs, tracklet IDs, floating support moments, detector scores, and
location responses. It fails closed on duplicate physical keys. The current
tracker already retains at most one candidate per source group in a track, but
the pipeline must still enforce uniqueness at this contract boundary.

An analysis receipt may add a separate, caller-attested
`conforms_to_standard_profile_digest`. It must retain the actual
`artifact_analysis_digest`; conformance must never alias or replace provenance.
The v2 partition may consume the named semantic profile digest after that
profile receives its own qualification.

This requires a new partition-policy and persisted-result contract version.
Snapshots and location receipts must carry both artifact provenance and the
partition-policy digest. All location fixtures and score thresholds require
requalification because v2 scores are not directly comparable with published
v1 scores. V2 would stabilize held-out assignment when physical supports and
semantic profiles agree; it would not make candidate or track IDs equal, and it
would not resolve the six known duplicate-rank identity ties.

No implementation experiment is justified until that contract and migration
are explicitly approved. The current v1 behavior remains truthful and frozen.

## Bounded standard-scorer isolator

The public server v1 scorer can validate a native analysis artifact without
claiming that artifact is the cached reference product. The pure
`score_point()` contract accepts track identity, observation identities, times,
measurements, a fixed training mask, candidate satellite IDs, tau values, and a
prediction tensor. It does not require the reference analysis digest.

The normal server preparation entry point is unsuitable for this isolator: it
reconstructs the cached server trajectory from its storage product and derives
that product's identities and mask. Instead, a report-local validator can read
each LOC1 fixture and its tracks audit, expose the fixture's exact native or
reference track inputs, Hermite-interpolate its saved orbit-state authority,
form `AdaptiveTrackPrediction` blocks, and call the frozen public
`score_point()` implementation. This uses the oracle only in the validator.
It adds no runtime dependency and injects no identity, mask, winner, or moment
from the other artifact.

The proposed test is bounded to the two registered sites and two existing
fixtures:

1. Run the reference LOC1 through the frozen Python scorer and require its 64
   satellite/tau winners and numeric track/point fields to match the frozen
   reference score. This validates the adapter.
2. Run the fresh-native LOC1 through the same scorer and require its 64
   satellite/tau winners and numeric fields to match the native C++ score.
3. Compare native and reference outcomes only after those two within-artifact
   checks. Keep their own observation IDs and masks; do not cross-substitute
   either fixture's authority.

Satellite IDs and tau values must be exact. Held-out RMS, training RMS,
frequency offset, and aggregate score use the existing `1e-6 Hz` absolute
tolerance, with finite-value rejection. The harness must bind the two LOC1 and
tracks-audit hashes, scorer sources, saved orbit authority, per-site inputs,
and complete serialized outputs. A 120-second host watchdog is sufficient;
there is no search and no hardware requirement.

Passing both cells would show that the standard scoring rule evaluates the
fresh native artifact consistently and that the old cached score is a result
for different persisted inputs. It would not prove cached-artifact identity,
isolate which upstream field causes each native/reference difference, validate
the normal server storage preparation path, or make the oracle a deployable
dependency. A failure would first localize the mismatch to adapter/prediction
formation or scoring arithmetic before any partition-policy change is
considered.

Frozen inputs for this experiment are:

| Input | SHA-256 |
| --- | --- |
| fresh-native LOC1 | `d9fa57b9a29f396a7aa71853ba784787b7fe382c66916ba2e609e23e4c910057` |
| fresh-native tracks audit | `8272123f6c4a26fe0349f8708bc93b4453b82f73e03e10ef9155b3685d683a9f` |
| public Python scorer | `ff64ecfa3dea9665b7ceb6536353364010af0e584a7b75aea472f0a43c4f5267` |
| public Python prediction contract | `b55e38ed27a0cd5f14fe8066307702a1fe19d56ba17b73c01fe138f0433dfcc0` |

The LOC1 already carries the exact saved satellite state grid used by the C++
score. The test should consume that grid directly. Repropagating the TLE would
introduce a separate SGP4 and frame-conversion comparison and would no longer
isolate the scoring rule.

### Executed result

[`standard-scorer-validation.json`](standard-scorer-validation.json) records a
PASS. The reference control ran first. At both sites its public Python scorer
selected the exact 64 satellite/tau winners; all per-track held-out RMS,
training RMS, and frequency offsets are exactly equal to the frozen score. The
aggregate differences are `2.84e-14` and `0.0` Hz.

The same frozen scorer then evaluated the fresh-native artifact with its own
IDs, measurements, and masks. It selected the exact 64 satellite/tau winners
at both sites, all per-track numeric fields are exactly equal to the native C++
score, and aggregate differences are `5.68e-14` Hz at each site. The complete
validator took 10.21 seconds and 118,600 KiB maximum RSS under the 120-second
watchdog. Five focused parser, weight, mask, interpolation, and horizon-filter
tests pass.

This closes the scoring-rule isolator: the public standard scoring rule
reproduces both artifacts when given each artifact's own identical inputs. The
fresh-native versus cached-reference score difference is therefore an input
artifact difference rather than a different scoring rule. This result still
does not assign the difference to one upstream identity, mask, measurement, or
moment field, and it does not compare TLE propagation or server storage
preparation.
