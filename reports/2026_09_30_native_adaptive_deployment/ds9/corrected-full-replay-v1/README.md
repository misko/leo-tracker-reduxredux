# Corrected full-recording replay

This report executes the complete 2,215-visit DS9 recording through the
isolated 22-slot deployed-server wrapper, the public projection and tracking
contracts, a fresh E2 location fixture, two registered-site scores, and two
bounded 400-point regional searches. It does not modify or promote the
ordinary production detector.

Every visit derives receiver geometry before reading a detector answer. The
public read-only recording store supplies the actual tuned IF, channel, edge,
sample rate, bandwidth, and LNB LO. The maintained Starlink contract supplies
the Qin pilot IF and template extent. All 4,430 receiver windows use a
-312,500 Hz receiver center and the maintained observable residual bounds.
Persisted candidates select no frequency parameter.

## Full detector result

[`full-output/summary.json`](full-output/summary.json) is PASS:

- 2,215/2,215 visits and 4,430 receiver windows completed with no failures;
- all visits are lower-edge because that is the complete DS9 inventory;
- 35,440 retained candidates and 24,681 complete candidate/gate rows were
  compared;
- all 24,681 native/current-server gate decisions match rank by rank;
- all 11,747 passing candidates match the persisted passing count;
- every persisted/current-server tested field is exact; and
- every retained native/current-server result is inside the frozen 1e-6 Hz
  and 1e-10 scalar tolerances.

The maximum native/current-server differences are 3.027e-9 Hz tracking CFO,
7.104e-12 samples fractional epoch, and 4.408e-13 margin. The four-worker run
took 1,419.47 seconds, used 264,320 KiB maximum RSS, retained no raw IQ, and
wrote compact resumable per-visit receipts. No partial failure receipt exists.

The earlier 32-visit balanced slice remains under `slice-output/`. It was the
review gate for the full run, not the final scope. Rejected harness-only runs
are preserved under `rejected-runs/` and are excluded from qualification.

## Public portable C3/C4 and physical comparison

[`full-public-c3-c4/report.json`](full-public-c3-c4/report.json) records the
public-store export. It re-read each recording event, counter, UTC/RF authority,
actual LO, and geometry. Persisted/current-server candidate values were not
used in projection or identity. The result contains 11,747 observations and
64 tracks using 3,372 observations.

[`full-public-c3-c4/reference-comparison.json`](full-public-c3-c4/reference-comparison.json)
compares identities only after pairing by physical source group and alias:

- all 64 track memberships, lanes, support bounds, and reference epochs match;
- all 3,372 relative alias indices match;
- maximum track-fit differences are 1.792e-10 slope, 1.874e-8 Hz intercept,
  8.348e-10 Hz RMS, and 2.910e-9 Hz maximum residual;
- graph support bounds match for all 11,747 observations;
- portable moment2 and moment3 lexemes match 5,160 and 132 rows respectively,
  while numerical differences remain at most 3.388e-21 and 3.746e-23; and
- exact candidate IDs, tracklet IDs, support digests, partition seeds, and
  complete masks are zero because those values bind the fresh native analysis.

All 64 tracks retain the same training cardinality, but only 1,770/3,372 mask
bits agree. The changed masks and location scores directly demonstrate
downstream partition sensitivity despite equal physical recovery and fits.
This comparison does not attribute every score difference to the masks alone.

The comparison is reproducible:

```sh
python3 compare_public_reference.py
```

[`partition-identity-design.md`](partition-identity-design.md) records the v1
identity and split formulas, quantifies the remaining moment sensitivity, and
proposes a versioned physical-support partition policy without substituting
reference provenance. Its bounded standard-scorer isolator also evaluates both
the cached reference artifact and the fresh-native artifact with the frozen
public Python score kernel. Both cells reproduce all satellite/tau winners and
per-track numeric fields exactly; aggregate differences are at most 5.69e-14
Hz. This establishes scoring-rule parity on identical artifact inputs without
making the oracle a runtime dependency.

## Explicit server-support profile lane

The portable output above is preserved. A separate opt-in lane under
`full-server-support-c3-c4/` derives support with the already-qualified
`server-x86_64-glibc-2.43-fma-python-repr-v1` profile. It uses the same fresh
native detector results and a new analysis digest that binds the detector,
templates, source inventory, profile manifest, projector, and tracker. It does
not borrow the reference analysis digest, moments, IDs, masks, or winners.

This lane matches 11,739/11,747 reference moment2 lexemes and 11,715/11,747
moment3 lexemes. The remaining 8 and 32 differences are consistent with the
already measured native fractional-input deltas. Physical memberships and fit
deltas remain unchanged. [`support-profile-comparison.json`](support-profile-comparison.json)
separates this numerical improvement from identity sensitivity.

The prior physical reference-identity control reproduced support digests,
partition seeds, and masks for 58 membership-identical tracks and isolated six
known duplicate-rank identity ties. That control explains the remaining C4
identity boundary, but its reference identities are not inputs here.

A separate physical ARM tracking check consumed the corrected native host
observations and emitted all 64 tracks byte-identically to the host output in
22.023 seconds. Its receipt is
[`../../tracking/corrected-native-arm-v1/comparison.json`](../../tracking/corrected-native-arm-v1/comparison.json).
That check did not execute detector or location work on ARM and is not a
continuous real-time claim.

## E2 and location

The adapter discarded the old LOC1 track payload and reused only receiver
sites, satellite identifiers, and orbit states. The fresh portable LOC1 has 64
tracks, 3,372 observations, and 1,998 training observations.

At the two registered sites, all 64 tracks match. Portable native scores are
226.7107329749787 and 412.74249165571746 Hz, versus reference scores
223.83559325001423 and 411.4285903855997 Hz. Satellite winners match on 60/64
tracks at each point; satellite plus tau match on 54/64 and 52/64 tracks.
These are partition-sensitive results, not missing-track counts.

The same fresh-native LOC1 and saved orbit states produced byte-identical host
and physical ARM fixed-site outputs: all 64 satellite/tau winners at both sites
and both aggregate scores match. The two-worker ARM run took 16.698 seconds.
See
[`../../location/corrected-native-arm-v1/comparison.json`](../../location/corrected-native-arm-v1/comparison.json).
This scope excludes regional search and fresh orbit propagation.

Both regional searches evaluated the fixed 400-point budget with
`complete=false`. Sacramento retained the reference incumbent offset
(-81.25 km east, -81.25 km north). Reno selected (-293.75, 206.25) km rather
than the reference (343.75, 81.25) km. Neither result is claimed as globally
converged. See
[`full-public-c3-c4/c7-search/summary.json`](full-public-c3-c4/c7-search/summary.json).

## Reproduction

The frozen full replay command was:

```sh
sudo -n timeout --signal=TERM --kill-after=10s 2100s \
  /var/tmp/leo-arm-realtime-publication/.venv/bin/python run_slice.py \
  --scope full --workers 4 --deadline-seconds 2080 \
  --output-dir full-output
```

The portable public export is reproduced with:

```sh
sudo -n /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  export_public_contract.py \
  --replay-output full-output --output-dir full-public-c3-c4 \
  --expected-visits 2215 \
  --projector public-export-artifacts/host/leo-project \
  --tracking public-export-artifacts/host/leo-tracking
```

The explicit support-profile lane is reproduced with:

```sh
sudo -n /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  export_server_compat_contract.py \
  --replay-output full-output --output-dir full-server-support-c3-c4 \
  --expected-visits 2215 \
  --projector server-support-artifacts/host/leo-project-server-compat \
  --tracking public-export-artifacts/host/leo-tracking \
  --profile ../../../../native/adaptive/runtime/server_compat/profile.json
```

Run the component tests and comparisons from this directory:

```sh
/var/tmp/leo-arm-realtime-publication/.venv/bin/python test_run_slice.py
/var/tmp/leo-arm-realtime-publication/.venv/bin/python test_export_public_contract.py
python3 test_compare_public_reference.py
python3 test_validate_standard_scorer.py
timeout 120s /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  validate_standard_scorer.py
python3 compare_public_reference.py
python3 compare_public_reference.py --native full-server-support-c3-c4
python3 compare_support_profiles.py
python3 compare_c7.py
```

The full qualification and limitations are frozen in
[`qualification.json`](qualification.json). This evidence uses saved data on
the host. It makes no live five-second freshness, ARM real-time, new RF, or
global-location-convergence claim.
