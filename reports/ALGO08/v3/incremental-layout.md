# Incremental solver updates on saved ALGO08v3 detections

Fixed model preparation accounts for **1.045 CPU seconds of eligible repeat work on DS30-0008** and **0.058 seconds on the independent southern near-edge simulation**. Reusing it reduced fixed constructions from 228 to 14 and 94 to 9, respectively. The solver made every original robust update and geographic projection. Both fitted and zero-calibration solutions reproduced the published evidence exactly. The dense construction ceiling covers 1.8% of the published 56.98-second solver stage. [Saved comparisons](measurements/incremental-layout.json) · [Published stage clocks](first-55/stage-clocks.csv)

## What changes during a solve

| Change | Reusable inputs | Work retained by the trial |
|---|---|---|
| Owner or integer alias | A retained track supplies the same timestamps, hardware and receiver basis rows. A satellite retains its causal orbit source. | Rebuild the layout and owner mapping. Candidate/alias changes can shift local phase and orbit columns, response offsets, active family priors, and the global fit. |
| Observation mask or held family | The full-row layout, radio design and nominal orbit coordinates keep their indices when the owners and arm stay fixed. | Reapply the observation mask, group weights and noise volume and rerun the robust solve. Held-family posterior covariance and predictive training use the selected mask. |
| Receiver position | At a fixed phase reference, interpolated satellite states are independent of the receiver position. The released model already holds those states. | Project the actual receiver location, rebuild Doppler and elevation-dependent values, and update the nuisance posterior. |
| Orbital phase reference | The static layout and priors remain available. | Resolve orbital phase interpolation, derivatives and the nonlinear observation model at the current reference. |
| Calibration arm | The input rows and causal archive remain available. | Keep distinct designs, references and fits for `c = 0` and fitted `c`. The fitted arm adds an RF-dependent receiver column that participates in the shared posterior. |
| Robust update | The existing native symbolic cache retains eligible layout structure. | Each original Gamma-precision iteration updates likelihood weights, normal factors, residuals and stopping behavior. |

The saved dense solve changed a track owner or alias at ten adjacent model constructions inside the same scan and traversed 45,220 rows at those boundaries. All 45,220 rows kept their track, and 36,888 kept both their satellite and alias. The southern solve changed an owner or alias six times across 1,596 rows, with 1,292 retaining both assignments. These are bounds on reusable row inputs. They leave global work coupled through the receiver, orbital, and robust terms. The site projection moved within the same instantiated model 685 times on the dense case and 287 times on the southern case. That work covered 3,097,570 and 76,342 row projections, respectively, even though the static layout remained available. [Saved work counts](measurements/incremental-layout.json)

## Same-layout reuse

The overlay splits the source-pinned `NormalPosition` constructor at the original observation-mask boundary. Within the installed solver, it keeps the last constructor layout for each calibration arm and a single current scan. A hit requires the same prepared scan object and its input identities and provenance, exactly the same seed and aliases, and the same scalar noise setting. The frozen solve owns those prepared inputs and treats them as fixed during the enrolled fits. A fresh problem gets independent copies of its layout arrays and receives the newly supplied phase reference and mask. The mask still enters the frozen validation and noise-volume calculation. The forecast/prior and likelihood closures are built by their original callers. The prototype applies to default point-noise models with explicit phase references. [Overlay](../../../tools/pipeline_eval/variants/algo08_incremental_layout.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_incremental_layout.py)

| Work through numerical evidence | DS30-0008, frozen → reuse | Southern near-edge, frozen → reuse |
|---|---:|---:|
| Fixed constructors | 228 → 14 | 94 → 9 |
| Rows in rebuilt fixed layouts | 1,031,016 → 63,308 | 25,004 → 2,394 |
| Reusable layouts with changed phase reference | 207 | 79 |
| Reusable layouts with changed observation mask | 31 | 8 |
| Geographic projections | 1,466 → 1,466 | 731 → 731 |
| Rows processed by robust likelihood calls | 5,405,522 → 5,405,522 | 192,850 → 192,850 |
| Robust likelihood calls | 1,466 → 1,466 | 731 → 731 |
| Gamma-precision updates | 39,251 → 39,251 | 10,404 → 10,404 |
| Row counts summed over precision updates | 162,531,152 → 162,531,152 | 2,754,696 → 2,754,696 |

Dense copying and snapshot construction consumed 0.145 CPU seconds. The keys and source checks added about 0.129 seconds in the instrumented prototype. Accounting for those costs bounds the saving at roughly **0.77 CPU seconds**. The corresponding southern accounting is **0.044 seconds**. On the dense solve, the full cost of the measured fixed preparation was 1.191 CPU seconds, even granting free preparation on every measured call. The row reduction supports exact reuse of the static scaffold. It leaves the solver far from the proposed 24-second budget. Earlier complete-call reuse and Schur-factor studies examined the remaining robust work and found limited exact opportunities. [Previous dependency audit](../single-core-2x/solver-fit-dependency-audit.md) · [Complete-call reuse](../single-core-2x/solver-exact-likelihood-reuse.md)

## Exact saved comparisons

Each process verified the installed ALGO08v3 specification, the saved detector packet and terminal, and the original region and causal TLE archive. Its clock began at the saved detector packet and ended after the numerical position evidence. It used the shared Gauss lock, CPU 2, nice 15, best-effort I/O priority 7, and one numerical thread. The first dense comparison ran reuse first, and the first southern comparison ran control first. Both comparisons instrumented the constructor and likelihood. The second dense comparison reversed the order and timed the final pinned overlay with the detailed diagnostics disabled. All replay modes reproduced the archived endpoints, RF RMS, owner, path and grid digests. The selected endpoint replay difference was zero in both arms on each input. The dense path retained all 356 native grid handoffs. The independent control kept 266 associated observations in both arms. The dense case kept 4,472 in both arms.

| Saved input and comparison | Frozen → reuse CPU s | Frozen → reuse wall s |
|---|---:|---:|
| DS30-0008, both timed with diagnostics | 57.007 → 53.113 | 57.054 → 53.280 |
| DS30-0008, plain frozen and final overlay | 56.909 → 54.892 | 58.207 → 55.227 |
| Southern near-edge, both timed with diagnostics | 4.759 → 4.484 | 4.787 → 4.484 |

Each row is one matched pair. The whole-run CPU differences exceed the measured constructor savings in both cases. The trial attributes only the directly accounted work to reuse. Fourteen component and adjacent position tests passed. [Saved receipts](measurements/incremental-layout.json)

| Saved input | `c = 0` / fitted RF RMS (Hz) | `c = 0` / fitted horizontal error (km) |
|---|---:|---:|
| DS30-0008 | 129.7030 / 129.6629 | 1.6390 / 1.5120 |
| Southern near-edge | 6.5023 / 6.3919 | 0.817 / 1.101 |

The geographic errors use the separately published reference scores. The southern fitted `c` lowers RMS while increasing horizontal error by 0.284 km. [DS30 reference scores](first-55/recordings.csv) · [Southern reference scores](../single-core-2x/solver-family-profile.md)

To replay either receipt, set `pair` to its original `pair.json`, choose a new output path, and run the following command from the research checkout. Omit `--reuse` for the instrumented control. `--plain` runs the released solver alone. `--reuse --no-audit` enables layout reuse with only the lightweight runtime counters.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
bench=/tmp/leo-algo08v2-2x-bench
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$payload:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/incremental_layout_trial.py \
  "$pair" "$new_receipt" --reuse
```
