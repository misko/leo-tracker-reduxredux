# Sealed secant optimizer on the 135-recording roof panel

Secant published all 135 positions in both calibration arms. All 121 fresh
replays completed in 36 min 44 s against the 38-minute cap. The other 14
positions came from the sealed timing and confirmation studies. Compared
with the compact projector, the worst increase in geodesic error was 76 m
with `c = 0` and 96 m with fitted `c`. Compared with original no-repair v5,
the worst increases were 1.140 and 1.148 km. [Per-recording scores](per-recording.csv)

The candidate changes the position optimizer in compact v5. The five-refresh
phase policy, original branches, full native GLRT observations, causal TLEs,
original 25 km tile and downstream cavity decision are shared. Both arms fit
the same observations, candidate roster and search budget. The standalone
candidate source and four compact dependencies match the original secant
timing source archive. [Preregistration](PROTOCOL.md) · [Frozen roster and schedule](roster.json)

The panel contains 127 DS26 and eight DS29 recordings. The candidate ledger
adopts six sealed timing predictions and eight disjoint sealed confirmation
predictions. Each prior timing prediction's original request digest is kept
beside the normalized full-panel case fingerprint. The supervisor scheduled
the other 121 in descending order of archived projector wall time before
scoring. The compact projector is the same-input archived control and the
four original v5 variants retain their original role requests. Conditional
frequency residuals are reported separately from geodesic error.

## Position accuracy

The table gives median, P95 and maximum geodesic error in kilometers. Each
method published every position, including 133 of 135 within 5 km in each arm.
[Accuracy and calibration distributions](summary.json)

| Cohort | Arm | Secant | Archived compact projector | Original no-repair v5 |
|---|---|---:|---:|---:|
| All 135 | `c0` | 0.977 / 2.936 / 7.161 | 0.982 / 2.941 / 7.269 | 0.982 / 2.941 / 7.269 |
| All 135 | `fitted_c` | 0.989 / 2.817 / 6.869 | 0.988 / 2.819 / 6.858 | 0.988 / 2.819 / 6.858 |
| DS26, 127 | `c0` | 0.987 / 3.073 / 7.161 | 0.988 / 3.084 / 7.269 | 0.988 / 3.084 / 7.269 |
| DS26, 127 | `fitted_c` | 1.004 / 3.121 / 6.869 | 0.999 / 3.126 / 6.858 | 0.999 / 3.126 / 6.858 |
| DS29, 8 | `c0` | 0.759 / 1.210 / 1.320 | 0.753 / 1.210 / 1.320 | 0.753 / 1.210 / 1.320 |
| DS29, 8 | `fitted_c` | 0.748 / 1.307 / 1.458 | 0.742 / 1.312 / 1.458 | 0.742 / 1.312 / 1.458 |

The paired counts below tally individual secant errors within +5% and +10%
of the comparator's error on the same 135 cases.

| Comparator | `c0` at most +5% / +10% | `fitted_c` at most +5% / +10% | Worst increase `c0` / fitted `c` |
|---|---:|---:|---:|
| Compact projector | 132 / 133 | 133 / 133 | 0.076 / 0.096 km |
| No-repair v5 | 129 / 131 | 129 / 131 | 1.140 / 1.148 km |
| Selective-gap | 128 / 130 | 127 / 129 | 1.134 / 1.160 km |
| Omitted-track-one | 120 / 125 | 120 / 126 | 1.140 / 1.148 km |
| Omitted-tracks | 117 / 122 | 117 / 123 | 1.140 / 1.148 km |

DS26-0152 had the largest error increase versus compact stock in both arms.
All four original v5 options had their largest penalty at DS26-0066. On that
recording secant moved the compact result by about 7 m with `c0` and 6 m with
fitted `c`, reducing its position error by about 5 m and 4 m. The compact
projector's error already exceeded original no-repair v5 by over 1.1 km on
that recording. The largest displacement from compact stock occurred on
DS26-0092 at 2.163 and 2.015 km. Its geodesic errors fell from 2.778 to
0.977 km and from 2.500 to 1.108 km. Compact-stock error worsened by more
than 1 m on 54 and 52 cases respectively, with zero increases above 100 m.
[Case outcomes](per-recording.csv) · [Candidate positions](v5_secant_fit.jsonl.gz) · [Stock positions](orbit_projector.jsonl.gz)

## Frequency evidence

The secant and compact projector's median conditional RMS was 71.169 Hz
with `c0` and 71.049 Hz with fitted `c`, equal to the displayed precision.
Original no-repair and selective-gap report median RF RMS of 109.782 and
98.146 Hz in the two arms. Both omitted-track options report 109.693 and
100.138 Hz. Those four values use the original v5 report's residual metric.
The paired candidate and compact arms used the same observation, track and
original branch counts on all 135 cases. [Frequency distributions by method and dataset](summary.json)

## Runtime and input provenance

The 121 fresh workers ran 60.48–390.79 s each, with median 129.88 s and
P95 236.94 s. The batch took 2,204.37 s on eight single-thread workers.
The fresh cohort included 120 DS26 and one DS29 recording. The eight prior
independent confirmation workers had a 96.13 s median and the six prior
paired candidate workers had a 108.11 s median. The separate six-case pair
experiment measured a 1.52× median paired speedup. The 167.38 s compact
archive median came from an earlier campaign.
[Supervisor and prediction receipt](receipt.json) · [Separate paired timing study](../../2026_11_19_receiver_convergence/position-fit/README.md)

Every prediction row includes native, causal catalogue, frozen request,
resolved request and matched-case digests. All four original v5 option
requests match the original tile, session, native observation and causal
catalogue snapshot history. All 540 recording-and-role pairs match the
frozen score fixture in both arms. Each fresh run has its own result digest, elapsed time,
CPU and deadline. The prediction lock predates the geographic score join.
[Prediction lock](prediction-lock.json) · [Original v5 role bindings](original-v5-inputs.json)

## Reproduction

Use the frozen native detector archive and scientific runtime. Start the
bounded worker supervisor on an unused scratch path and keep the shell work
separate from scoring. The production invocation used a detached user
service, a 38-minute cgroup runtime cap and one numerical thread per CPU.
It gave each active worker the smaller of 480 s and the remaining replay
time after reserving five seconds for the terminal journal. The shorter
deadline applies only at the end of the schedule.

```sh
secant_work=$(mktemp -d /srv/bulk/leo-dev/leo-secant-full.XXXXXX)
systemd-run --user --unit="leo-secant-full-${secant_work##*.}" --wait --collect \
  --working-directory="$PWD" --property=RuntimeMaxSec=2280s \
  --property=KillMode=control-group --property=KillSignal=SIGKILL \
  --property="StandardOutput=append:$secant_work/replay.log" \
  --property=StandardError=inherit --setenv=OPENBLAS_NUM_THREADS=1 \
  --setenv=OMP_NUM_THREADS=1 --setenv=PYTHONUNBUFFERED=1 \
  /usr/bin/taskset -c 12-19 "$PWD/.venv/bin/python" \
  -m tools.pipeline_eval.qualification.secant_full run \
  --work "$secant_work" --output "$secant_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.secant_full seal \
  --work "$secant_work" --output "$secant_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.secant_full score \
  --output "$secant_work/report"
```
