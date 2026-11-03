# Timestamp convention audit

No export-origin or timestamp-roundtrip discrepancy was found in the frozen 64-scan corpus. All 190,896 exported evidence points reproduce their original relative times exactly after integer UTC conversion. Every exported capture start equals the corresponding selected capture-start metadata. This includes tracks later excluded by the estimator; the point count is not the number of independent observations used in fitting.

`timestamp-roundtrip-v1.json` and its SHA seal record all 64 outcomes and input bindings. The audit matches sessions and manifests, verifies each parent prediction seal, binds evidence and source exports to the parent's recorded input hashes, joins unique track IDs, verifies monotone times, and compares every timestamp. It does not re-export raw candidate evidence or independently verify hardware UTC.

## Inspected timestamp path

The pinned deployed `scanner_trajectory.py` subtracts the integer session-start device counter from the valid-start counter before adding fractional sample positions. It then adds the probe sample offset and the local GLRT support center, converts the relative sample count to nanoseconds, rounds, and adds the first-sample UTC estimate. This avoids converting large absolute device counters directly to floating point.

The support-geometry function constructs the actual selected GLRT symbol intervals, excludes unsupported intervals using fractional-sample guards, and takes the arithmetic mean of their sample centers. The timestamp is therefore the mean supported-symbol time, rather than the beginning or midpoint of the entire probe. It also records second and third support moments around that center.

The baseline exporter checks public projected support-center times against prepared numerical times before writing `times_s`. The frozen estimator loader subtracts the integer capture start from integer UTC evidence before division by 1e9. The all-64 roundtrip verifies the latter conversion against the exported relative times.

Inspected source root:
`/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/lib/python3.14/site-packages/leo/application/`

- `scanner_trajectory.py`: SHA256 `844f23c068af8c6f6a0477f1a0ce2997e1066b2585d4cbca24781f62ab8c3e7b`.
- `persistent_hop_trajectory.py`: SHA256 `05d769be631055c2d91d8b8175c6c432c2921ebc0d3da00a8fe46c345ece8252`.

These were inspected read-only. Source inspection establishes the implemented formula; the numerical roundtrip establishes preservation of exported times. Neither alone independently validates the original physical sample epoch. No source, contract, fixture or estimator timing parameter was changed.

## Implication and next step

There is no evidence here for correcting all observations by half a probe duration or changing the capture origin. Previously tested receiver-specific timing fits remain distinct from this source audit and do not establish a hardware clock fault.

One narrower approximation remains: the localization model predicts instantaneous Doppler at the supported-symbol mean time, whereas the frequency estimator uses a finite set of symbols. Before any nonlinear experiment, bound the difference between point prediction and support-averaged prediction using the recorded support durations and orbital curvature. This should first be a reference-free magnitude calculation, with prior support-moment work reviewed; do not assume it can explain kilometers or fit a new timing offset to GPS.

No geographic estimate changed. The benchmark remains 2,059.90 m median error, 5,850.75 m p90, and 64/64 acceptance. Accuracy and independent uncertainty-calibration targets remain unmet.
