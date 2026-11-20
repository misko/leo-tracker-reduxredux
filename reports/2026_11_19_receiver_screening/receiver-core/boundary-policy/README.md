# Paired 20 m tile-face guard on installed compact v5

The guard preserved **all four legitimate offers** and stopped **all four false regional fixes** across two fresh simulated sites, in both calibration arms. The unguarded phase-release receiver published all eight offers. Every omitted-offer estimate reached a face of the fitted rectangle. The guard preserved those exact coordinates as forced diagnostics and left conditional RF RMS unchanged. [Fresh figure, fitted `c`](charts/fitted_c/boundary-policy-fresh.png) · [Fresh figure, `c = 0`](charts/c0/boundary-policy-fresh.png) · [Per-site and per-arm scores](scores.csv)

The rule is the previously sealed `compact_tile_interior.guard`. It withholds both arms when either selected point is at most 0.020 km from the nearest face in the receiver's exact linear coordinates. The 20 m tolerance is the optimizer's existing secant stopping scale. Each of the eight offers ran one numerical call on the same installed phase-release binary and source hashes as the preceding four-site test. The stock and guarded decisions use the same output. [Frozen protocol](PROTOCOL.md) · [As-run guard and installed source identities](source-lock.json) · [Original guard qualification](../../deployment/transfer-budget/interior-guard/README.md)

## Fresh blind sites

The seed drew one site in the western Pacific and one in southern South America, respectively 4,298 and 2,172 km from the closest earlier location in the compact guard and compact-blind panels we audited. Each site contributed four independently blinded offers on one simulated 300 s dual-receiver factor stream. Truth margins are defined in the solver's 25 km rectangle. Replay used the earlier seeded wideband simulator with new transmitters, earlier TLE availability, clock skew, transmitter epoch and carrier errors, RF-dependent calibration, correlated noise and gated alternatives. This is a native-factor positioning test. [Prospective input seal](input-lock.json) · [Public offers and exact native digests](requests.json) · [Labels released after both decisions were sealed](truth-after-lock.json)

| Site | Valid publications before → after, either arm | Legitimate withholds added, either arm | False regional fixes before → after, either arm |
| --- | ---: | ---: | ---: |
| Western Pacific | 2/2 → 2/2 | 0/2 | 2/2 → 0/2 |
| Southern South America | 2/2 → 2/2 | 0/2 | 2/2 → 0/2 |

| Offer | Published before → after, either arm | Median selected or forced error, zero / fitted | Median conditional RF RMS, zero / fitted |
| --- | ---: | ---: | ---: |
| Interior | 2/2 → 2/2 | 0.644 / 0.608 km | 38.463 / 38.447 Hz |
| 1.5 km inside | 2/2 → 2/2 | 0.645 / 0.606 km | 38.463 / 38.447 Hz |
| 1.5 km outside | 2/2 → 0/2 | 1.628 / 1.598 km, forced | 38.304 / 38.295 Hz |
| 27.5 km outside | 2/2 → 0/2 | 30.207 / 30.207 km, forced | 39.332 / 39.314 Hz |

The retained near-inside solutions were at least 1.586 km inside their fitted offers. All eight omitted-arm selections were on a fitted face to within (10^{-9}) km. The near-omitted model's RF residuals were comparable to the valid offers, so the RF numbers are reported separately from the geographic decision. The guard's evidence covers fits that contact the tile face. An interior fit can still be a false publication in a wrong region. [Both-arm cross-tabs](summary.json) · [Prediction seal](prediction-lock.json)

The eight installed numerical calls took 52.10–82.37 s wall (median 58.98 s), 46.29–74.27 s process CPU (median 51.81 s), and 276.4–311.8 MiB process peak RSS. The resource timer enclosed the installed process inside its namespace. The opt-in CLI subprocess took 0.167–0.495 s wall (median 0.221 s), including Python startup and JSON handling. The numerical position is computed once, so the guard adds no second fit. It runs after numerical work and therefore supplies no recovery-stage deadline savings. The two pinned lanes finished in 254.3 s. [Raw CLI outputs and process accounting logs](cli-outputs.tar.gz)

## Retrospective evidence

On the earlier four-site test, each installed profile kept all four containing publications and stopped all four near-omitted publications. Both profiles previously selected identical endpoints and residuals. The archived endpoint and guard are assessed on the same original tile, with no fresh numerical runs in this panel. [Phase-release figure](charts/fitted_c/boundary-policy-archived-phase-release.png) · [Base compact figure](charts/fitted_c/boundary-policy-archived-compact.png)

On the earlier two exact phase-release roof waveforms, the guard retained both containing publications in both arms. Their original positional wall times were 50.58 and 33.48 s. The authenticated DS26-0036 portable exact compact reattempt with a 7 km shifted containing offer stopped at its deadline and supplied no selected estimate to the guard. These historical measured inputs contribute two publications and one genuine no-estimate. The evidence here covers the measured containing offers. [Measured historical figure](charts/fitted_c/boundary-policy-measured.png) · [Earlier phase-release waveforms](../../acquisition-support/fresh-waveform/README.md) · [Exact shifted-roof reattempt](../../redesign/compact-transfer/README.md) · [Retrospective source seals](retrospective-sources.json)

## Opt-in command

Pass the installed receiver's JSON output on stdin, declaring the exact fitted tile. Omitting `--interior-guard` forwards the input bytes unchanged. The eight prospective controls exercised that CLI path and verified exact output equality. The opt-in outputs were independently checked against the sealed paired guard. [Runnable decision entry](../../../../tools/pipeline_eval/variants/compact_tile_decision.py) · [Both CLI byte hashes per offer](positions.jsonl.gz)

```sh
.venv/bin/python -m tools.pipeline_eval.variants.compact_tile_decision \
  --interior-guard --tile "$LATITUDE" "$LONGITUDE" < installed-result.json
```

For a repeat, copy `PROTOCOL.md` into a fresh report directory and supply an authenticated installed phase-release tree and the prior truth-free catalogue archive. Use the seed from the released label receipt to reproduce these generated factors.

```sh
nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 14,15 .venv/bin/python -B -m tools.pipeline_eval.qualification.boundary_policy_trial \
  stage "$WORK" --out "$OUTPUT" --seed-hex "$SEED"
nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 14,15 .venv/bin/python -B -m tools.pipeline_eval.qualification.boundary_policy_trial \
  predict "$WORK" --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.boundary_policy_results \
  "$WORK" --out "$OUTPUT" --render
```
