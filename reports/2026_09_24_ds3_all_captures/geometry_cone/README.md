# DS3 LT3D-001A geometry and cone model track

This directory provides the report-local eligibility adapter and closed model
specifications for the DS3 top-ten comparison. It reads only recording
manifests. It does not read IQ, mutate capture storage, or use a reference
coordinate.

## Capture-time authority

The binding audit found five Sep 24 captures with an explicit, time-valid
`LT3D-001A` receiver-geometry binding:

- `scan-fw-f3ce5fe73aa40506`
- `scan-fw-9f3d5067d149118e`
- `scan-fw-cfcf667726e80735`
- `scan-fw-294be7850b76a34d`
- `scan-fw-ff02a0ba4200d0dc`

All carry binding digest
`sha256:55e5a117d885e8ac158a0a41895b66cb5be881d66630d2765fccf5711a21643f`.
The first three are the bindings already carried into the DS2 manifest. The
last two are receipt-V6/schema-12 captures whose own recording manifests carry
the same binding. The DS3 summary flag is deliberately not an authority for
this adapter.

Every other DS3 capture is excluded from geometry/cone models with
`capture_time_geometry_absent`, even when it used the same radio family or was
recorded on the same date. A binding outside its validity interval, a fixture
digest mismatch, incomplete receiver assignments, or an unsupported mapping
status is also an explicit exclusion.

The physical receiver-to-slot mapping is provisional, so all runnable models
must marginalize the identity and swapped mappings symmetrically. The fixture
contains nominal mount axes but no measured RF boresights or RF phase centers.
Results must therefore say `fixture_nominal_mount_axis_proxy`; they are not an
antenna-pattern or calibrated-pointing measurement.

## Closed model variants

The adapter emits four candidates for consideration in the top-ten comparison:

1. `lt3d_geometry_only`: receiver-label likelihood using the closest transformed
   nominal mount axis, with yaw and at most 15 degrees of tilt fitted on training
   data.
2. `lt3d_fixed_up_cone`: zenith-fixed cones at the previously tested 10, 15, 20,
   and 30 degree half angles (20, 30, 40, and 60 degree full FOV). Select one on
   development data, then freeze it.
3. `lt3d_learned_zenith_cone`: fitted yaw, cone width, and direction constrained
   to at most 15 degrees from zenith.
4. `global_time_plus_lt3d_cone`: the same constrained cone with one shared global
   time-offset nuisance parameter; every participating capture must have
   qualified UTC timing.

These specifications follow the bounded prior work in
`2026_09_23_train_fixed_cone`, `2026_09_23_train_pointing_cone`, and
`2026_09_24_ds2_geometry_cone_evaluation`. They still require a join to
receiver-labelled causal track evidence before running. Missing receiver labels,
candidate state support, a randomized partition, or qualified timing for the
global-time variant excludes that model/session rather than weakening the gate.

No variant accepts relative receiver phase, a fitted receiver phase offset, or
any baseline/direction inferred from phase. The current receiver phase is not
calibrated for geometric inference.

## Read-only preparation

The CLI writes JSON to stdout so privileged capture reads do not create
root-owned report artifacts:

```bash
sudo -n .venv/bin/python \
  reports/2026_09_24_ds3_all_captures/geometry_cone/prepare.py \
  --manifest reports/2026_09_24_ds3_all_captures/manifest.json \
  --capture-root /srv/bulk/leo/scanner-adaptive-recordings \
  > /tmp/ds3-lt3d-geometry-cone-plan.json
```

This command reads 56 small JSON manifests and no sample data. Review the plan
before copying it into a report-local output. It never writes beneath
`/srv/bulk` or `/mnt/qnap01`.

## Sealed result qualification

After the two staged inference artifacts and the shared-time control are
sealed, combine them into the four-row machine-readable summary:

```bash
.venv/bin/python \
  reports/2026_09_24_ds3_all_captures/geometry_cone/combine_summary.py
```

The combiner validates every input's sibling SHA-256 seal, the exact four model
IDs and five-session set, joint-five diagnostics, the no-reference declarations,
and the expected orientation modes. It selects cone scenarios only by the
development training objective. The global-time model reuses the learned-cone
result only when `global_tau_s` equals `0.0` exactly and records both the learned
artifact and time-control seals; any nonzero or missing value fails closed.

The output is `output/geometry/geometry-model-summary.json` with a sibling
`.sha256` seal. Existing summary or seal files are never replaced.
