# Installed compact v5 on four new simulated receiver sites

This study starts with generated native GLRT candidates. It evaluates the installed `phase-release` and base `compact` profiles on byte-identical wideband candidates, matched TrackConfig and genuine causal TLE collections. Both programs solve both calibration arms under the same single 25 km tile and sky-screen center. The independent measured wideband transfer remains unmeasured. [Frozen protocol](PROTOCOL.md) · [Public native requests](requests.json) · [Installed source and binary hashes](executables.json)

## Published coverage and false fixes

The two installed profiles produced identical coordinates and conditional Doppler RMS on all eight requests in both calibration arms. Each published **4/4 containing fixes within 5 km** and **4/4 false regional fixes** on the near-omitted offers. Every omitted-offer coordinate remained inside the wrong tile. The offer's nearest face was about 1.5 km from the receiver, so a position can have a small absolute error and still be a false regional fix.

| Profile and offer | Publications, either arm | False regional fixes, either arm | Median error, zero / fitted | Median conditional RF RMS, zero / fitted |
| --- | ---: | ---: | ---: | ---: |
| Phase release, containing | 4/4 | 0/4 | 1.286 / 1.201 km | 38.728 / 38.705 Hz |
| Phase release, near omitted | 4/4 | 4/4 | 1.723 / 1.691 km | 38.671 / 38.657 Hz |
| Base compact, containing | 4/4 | 0/4 | 1.286 / 1.201 km | 38.728 / 38.705 Hz |
| Base compact, near omitted | 4/4 | 4/4 | 1.723 / 1.691 km | 38.671 / 38.657 Hz |

The median paired fitted-minus-zero changes were −0.008 km and +0.003 Hz on containing offers and −0.045 km and +0.016 Hz on omitted offers. These are the median of per-offer differences. The table gives the two arm medians separately. Results cover all four offers in each condition. [Scores by offer and arm](scores.csv) · [Distributions and matched differences](summary.json) · [Prediction seal](prediction-lock.json)

The batch finished in 601.4 s across two pinned CPUs. Whole-process wall time was 47.57–119.97 s for phase release, median 66.15 s. Base compact took 45.16–108.24 s, median 63.47 s. These wall times include namespace startup and factor decoding and reflect shared host contention. They are separate from the simulated acquisition's 300 s duration. [Fitted phase-release figure](charts/fitted_c/compact-blind-phase-release.png) · [Zero phase-release figure](charts/c0/compact-blind-phase-release.png) · [Both profile and reference charts](charts/manifest.json)

## Same-input original numerical comparison

The regional harness reproduced the archived full-original v5 roof result in both arms and through all 18 stages before opening the two new offers. Its off-roof path holds the original numerical engine fixed and replaces the fixed-publication-geometry entry. This comparison covers one simulated site. [Reference protocol](../v5-regional-reference/PROTOCOL.md) · [Roof parity](../v5-regional-reference/roof-retry/parity.json) · [Reference prediction seal](../v5-regional-reference/prediction-lock.json)

| Receiver and offer | Status | Error, zero / fitted | RF RMS, zero / fitted | Worker wall |
| --- | --- | ---: | ---: | ---: |
| Original numerical reference, containing | Published | 1.773 / 1.372 km | 38.840383 / 38.792337 Hz | 161.68 s |
| Installed phase release, containing | Published | 1.774 / 1.364 km | 38.840371 / 38.792408 Hz | 79.49 s |
| Original numerical reference, near omitted | Timed out | — | — | 240.28 s |
| Installed phase release, near omitted | False regional fix | 1.768 / 1.639 km | 38.976658 / 38.941943 Hz | 47.57 s |

The completed containing endpoints agree within 8 m in both arms. The original omitted attempt exhausted its wall budget, so its ability to reject that offer remains unknown. The reference was on a different CPU and ran the full publication stages. [Fitted reference figure](charts/fitted_c/compact-blind-original-numerical-reference.png) · [Zero reference figure](charts/c0/compact-blind-original-numerical-reference.png) · [Matched score seal](score-lock.json)

## Input and timing authority

The four seeded positions are independent draws within previously unused North African, South American, central Asian and southwest Pacific boxes. Each 300 s case has 13,636 candidate probes across all 16 receiver-channel lanes and 2,991–3,042 probe rows with a passing peak. The generated factors include retarded orbital Doppler, separate RF edges, clock skew and offset, transmitter phase and frequency nuisances, receiver drift, a signed RF calibration term, correlated noise, rivals, and misses. The 35 TLE collection records contribute 23 unique element snapshots, all collected before each capture cutoff. The compressed native files expand to the exact SHA-256 in the eight truth-free requests. The replay starts at native factors. [Causal authority](catalogue-authority.json) · [Input commitment](input-lock.json) · [Source and release lock](source-lock.json)

There is one containing offer and one near-omitted offer per site. The containing tile center is 7–10 km from truth. For the omitted offer the receiver lies approximately 1.5 km beyond the nearest face. The input bundle withholds the true station, altitude, satellite identities, clock error and calibration from every worker. Each candidate is an isolated invocation on CPU 14 or 15 with one numerical thread and a 175 s wall limit. The outer wall clock covers the installed process from prepared-file input. Internal stage clocks cover preparation and fitting. The external resource timer observed the namespace launcher, which reparented the numerical process. Its raw CPU and RSS counters remain in the prediction archive for inspection. The scientific score table leaves those counters blank for both installed profiles.

The unchanged original v5 job rejected the off-roof request at its `search_center` validation. Its publication validator requires the fixed historical roof frame. The installed base `compact` build provides the full-roster comparison. [Exact original-job preflight](unchanged-v5-preflight.json)

## Reproduce

Use a new directory on local ext4, pin the worker lanes and place the compiler's temporary directory on that same volume. To reproduce the released native packets, pass the 32-byte seed from the post-commitment evaluator receipt to `prepare`. The input commitment applies to the full seeded roster. [Truth and seed after the prediction lock](truth-after-lock.json)

```sh
cp reports/2026_11_19_receiver_screening/receiver-core/compact-blind/PROTOCOL.md "$OUTPUT/"
nice -n 10 taskset -c 14,15 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.compact_blind_trial prepare "$WORK" --out "$OUTPUT" \
  --seed-hex "$SEED"
mkdir "$WORK/compile-tmp"
nice -n 10 env TMPDIR="$WORK/compile-tmp" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 14,15 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.compact_blind_trial predict "$WORK" --out "$OUTPUT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_blind_results \
  "$WORK" --out "$OUTPUT" --reference-seal "$REFERENCE_SEAL" --render
```
