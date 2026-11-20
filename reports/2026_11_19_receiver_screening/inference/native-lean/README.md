# Streaming native GLRT to position

The archived-factor receiver achieved **150.5 MiB peak RSS and 3.57 s median wall time** on one pinned x86-64 core. It published both calibration arms on four of five recordings under a hard **512 MiB virtual address-space limit**. Each freshly prepared control produced byte-identical canonical anonymous tracks and identical publication decisions, forced coordinates, calibrated coordinates and frequency scores. The smaller receiver missed the near-v5 accuracy target on this roster.

## Measured boundary

The worker starts from the complete stored capture-era native GLRT archive, a timestamp-bound causal orbit catalogue, the capture’s track configuration and one supplied 25 km region. It reads and hashes the archive in 64 KiB blocks, keeps one accepted peak per probe, runs the existing Graph lane fitter, and applies the same causal exact robust fitter as the prepared-track control. The fitter uses coarse 20 s and regional 5 s orbit samples, held-track and geometry gates, and the two matched RF calibration arms. Reference endpoints are opened by the supervisor after both arms finish. The native worker has no prepared-track mount. This replay covers GLRT factors through position. IQ detection, RF acquisition, unconstrained global region selection and physical Arm timing are outside the measured interval.

| Worker boundary | Median CPU | Median elapsed | Max RSS | Max virtual |
| --- | ---: | ---: | ---: | ---: |
| Native stored GLRT through position | 3.13 s | 3.57 s | 150.5 MiB | 386.0 MiB |
| Prepared tracks through the identical fitter | 1.38 s | 1.82 s | 148.7 MiB | 385.4 MiB |

The native elapsed range was 2.01–4.21 s across the five cases. Native median stage CPU was 0.12 s archive read and peak selection, 1.61 s Graph fitting, 1.03 s orbit search and position fitting, and 0.36 s numerical imports. The control’s separate frozen materialized Graph preparation took 2.57 s median elapsed. Its median total serialized preparation and fitter interval was 4.22 s. Reads used the local archive and the Linux page cache. The 256 MiB resident target is verified by measured `VmHWM`. Only virtual memory had an enforced cap.

Every final measured worker ran from the staged first-party source closure, **17 Python files and 3,590 physical lines**. The initial untrimmed import of the same smoke worker needed 32 files and 9,155 lines. The staged bundle removes two eager package initializers and the unrelated modules they import. The initial and staged workers returned identical smoke tracks and fits. Python and installed third-party numerical packages are outside the source-line counts and contribute to the measured process memory. [`deployment.json`](deployment.json) records the exact file list and hashes. The qualification supervisor builds the same source closure in its scratch directory.

## Accuracy and publication

| Recording | Cohort | Streaming or prepared error, c=0 / fitted (km) | Original v5 error, c=0 / fitted (km) | RF RMS, c=0 → fitted (Hz) |
| --- | --- | ---: | ---: | ---: |
| DS26-0036 | Smoke | 1.667 / 0.984 | 1.278 / 1.208 | 166.2 → 134.7 |
| DS29-0082 | Smoke | 3.779 / 3.250 | 0.567 / 0.517 | 267.0 → 213.9 |
| DS26-0187 | Confirmation | 1.182 / 1.076 | 2.267 / 2.389 | 178.6 → 137.0 |
| DS26-0197 | Confirmation | Withheld / withheld | 0.528 / 0.689 | 202.3 → 170.6 |
| DS29-0519 | Confirmation | 0.562 / 0.793 | 0.248 / 0.319 | 147.0 → 95.1 |

Published-error median and interpolated p95 were 1.424 and 3.462 km for `c=0` and 1.030 and 2.924 km for fitted `c`, each from 4/5 attempts. The original v5 published all five with medians of 0.567 and 0.689 km. Counting all attempts, 1/5 of the lean `c=0` runs and 2/5 of the fitted runs were within 10% of original v5 error or better. The counts are the same at 5%. The withheld correct-region run failed the geometry gate. Fitting `c` reduced conditional RF RMS on all five recordings. It reduced error on three of four published fixes and increased error on DS29-0519.

In the separately sealed recorded wrong-region test, both workers withheld both arms for `weak_held_track_support` on the frozen `r0` offer. The forced coordinates were 22.560 km from truth in both arms. The held-track score fell from 0.548 on the original offer to 0.221. The transfer sample contains one recorded case.

## Reproduction

The Linux reproduction requires the frozen corpus, the repository environment and Bubblewrap. Choose an available CPU and run from the repository root.

```bash
scratch=$(mktemp -d /tmp/native-lean.XXXXXX)
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.native_lean_eval \
  --cpu 6 --work "$scratch/work" --out "$scratch/evidence"
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --evidence "$scratch/evidence" --out "$scratch/charts"
.venv/bin/python -B -m tools.pipeline_eval.qualification.gallery_check \
  "$scratch/charts" --expected-charts 3
```

[Protocol](PROTOCOL.md) · [All errors and decisions](errors.csv) · [Predictions](positions.jsonl.gz) · [Prepared control](control-positions.jsonl.gz) · [Wrong-region predictions](wrong-positions.jsonl.gz) · [Chart definitions](figures.json)
