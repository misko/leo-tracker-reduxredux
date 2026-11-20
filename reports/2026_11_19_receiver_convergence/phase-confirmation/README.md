# Independent confirmation of two early phase fits

The two-refresh budget published all 21 confirmation fixes in both calibration
arms. Median position error rose from 0.674 to 0.841 km with `c = 0` and from
0.758 to 0.956 km with fitted `c` relative to the matching compact projector.
Nine cases per arm worsened by more than 100 m. All fixes remained within
5 km. [Per-recording scores](per-recording.csv)

The two-refresh candidate caps early orbit phase linearizations at two in
initial branch fits, conservative recovery, salvage and family fits. It
retains the full native GLRT observation set, original branch proposal search,
signed correction and cavity decision. Both calibration arms use the original
25 km roof tile and the same causal catalogue. The 21 confirmation recordings
contain 16 hash-selected DS26 recordings and the five DS29 recordings outside
the timing cohort. [Preregistration](PROTOCOL.md) · [Frozen roster](roster.json)

The reference side includes the archived compact projector and all four
original v5 options. Each confirmation request matches the compact projector
input hash. The original role audit authenticates its native hash, causal
catalogue, session, full causal snapshot mapping, request receipt and tile.
The scoring step also checks original role endpoints against the frozen
comparison fixture after prediction lock. The candidate replay begins at the
stored native detector results. [Candidate source lock](source-lock.json)

## Position accuracy and frequency fit

The table gives median, P95 and maximum position error in kilometers on
matched inputs. All methods published every position. Across all 21
recordings, the original v5 repair options match the displayed no-repair
statistics to rounding except for the 0.747 km fitted-`c` median of
omitted-tracks.
[All six methods, both arms](summary.json)

| Cohort | Arm | Two refreshes | Compact projector and no-repair v5 |
|---|---|---:|---:|
| All 21 | `c0` | 0.841 / 2.709 / 3.192 | 0.674 / 2.833 / 3.191 |
| All 21 | `fitted_c` | 0.956 / 2.691 / 3.356 | 0.758 / 2.486 / 3.356 |
| DS26, 16 | `c0` | 0.910 / 2.829 / 3.192 | 0.722 / 2.923 / 3.191 |
| DS26, 16 | `fitted_c` | 0.969 / 2.857 / 3.356 | 0.774 / 2.703 / 3.356 |
| DS29, 5 | `c0` | 0.646 / 1.184 / 1.226 | 0.621 / 1.002 / 1.007 |
| DS29, 5 | `fitted_c` | 0.561 / 1.194 / 1.235 | 0.567 / 1.035 / 1.041 |

Against no-repair v5, 11 of 21 cases in `c0` and 10 in `fitted_c` were at
most 10% worse. Twenty coordinates per arm moved more than 1 m from the
compact projector. The largest increase in position error occurred on
DS26-0040 in both arms, at 0.864 and 0.875 km respectively. The compact
projector and no-repair v5 had 19 of 21 fixes within 2 km in each arm.
Two refreshes had 18 in each arm.

Median conditional RF RMS changed from 72.73 to 72.48 Hz with `c0` and
72.69 to 72.45 Hz with `fitted_c` relative to the compact projector. The
candidate made 325 early fit calls and used two rounds in every call. The
observation, branch and track counts were identical on each paired recording.
[Sealed candidate positions](v5_two_refresh.jsonl.gz) · [Archived stock positions](orbit_projector.jsonl.gz)

## Runtime and provenance

The confirmation workers ran for 62.01–279.78 s per recording, with a median
of 128.11 s and a batch elapsed time of 843.52 s. The corresponding median in
the historical compact projector archive was 141.16 s.
[Confirmation receipt](receipt.json) · [Original role bindings](original-v5-inputs.json)

The six separate fresh timing pairs matched inputs, catalogues and CPUs and
published both arms. The candidate was faster on five recordings. The
median paired stock-to-candidate elapsed-time ratio was 1.27×, with a range
of 0.78×–1.76×. The timing study repeated DS26-0122 to obtain its supervisor
elapsed time and retained the interrupted numerical result separately.
[Timing study](../phase-budget/README.md) · [Timing receipt](../phase-budget/receipt.json) · [Interrupted attempt](../phase-budget/interrupted-attempt.json)

## Reproduction

The standard worker has a 480 s elapsed-time deadline per recording. The
confirmation launch uses one numerical thread on each of cores 16–19 and
allows at most four active workers. The six prescheduled timing cases are
reported independently in the neighboring phase-budget directory. The
archived compact-projector times for confirmation are historical measurements.

```sh
taskset -c 16-19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m tools.pipeline_eval.qualification.phase_confirmation run --cpus 16 17 18 19 \
  --source-lock reports/2026_11_19_receiver_convergence/phase-confirmation/source-lock.json
.venv/bin/python -m tools.pipeline_eval.qualification.phase_confirmation seal
.venv/bin/python -m tools.pipeline_eval.qualification.phase_confirmation score
```
