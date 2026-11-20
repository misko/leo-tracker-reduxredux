# Compact secant on the DS26 roof complement

The first budget launched **23 of 31 eligible recordings** on six low-priority lanes. Compact secant published both arms on **16**, with six numerical failures and one timeout. Eight eligible cases remained unlaunched and the frozen unavailable case retained its input status. [Run receipt](run-receipt.json)

The scheduled roster is the exact 32-recording difference between the frozen `ds26-all159` and `ds26-common127` sets. Thirty-one records have authenticated capture-era native factors, a causal catalogue, an original 25 km tile, and the original blind baseline request. DS26-0172 has the frozen `no_native_run` disposition. The dispatch order hashes IDs under a fixed prefix. Historical outcomes have no role in dispatch or input eligibility. [Protocol](PROTOCOL.md) · [Frozen roster and input bindings](roster.json)

The candidate is the unchanged five-round compact secant worker with the original initial search budget. It receives the archived capture-era native inputs and rebuilds the position from them. The read-only original baseline request authenticates even where the original numerical worker crashed. Both calibration arms use the same observations, candidate selection policy and tile. [Candidate positions](positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

The scheduler uses a 195-second worker cap and a shared 12-minute dispatch window. It launches only when a complete worker slot remains. A scheduled eligible row without a launch has status `missing` and retains its bound inputs. A case with unavailable input retains its actual archival disposition. Each fresh attempt records its status, worker elapsed time and whether the scientific worker returned a decision. An inner exception reported by the legacy launcher is recorded as a numerical failure with the original launcher status and exception retained. [Per-attempt receipts](run-receipt.json)

The four capture-era v5 comparisons retain all original outcomes, including observed failures, timeouts and missing inputs. An independent check links each frozen evaluation row to its archived role's execution, exact request digest, matching tile, causal TLE and native factors where available. The comparison keeps the compact conditional RF RMS, captured publication RMS and archived matched-observation RMS as distinct quantities. [Original role outcomes](original-roles.json) · [Original role bindings](original-role-bindings.json) · [Both calibration arms](scores.csv) · [Score seal](score-lock.json)

## Matched 23 attempted recordings

The original role counts use exactly the same physical recordings as the compact attempts. Compact conditional Doppler RMS medians were 68.927 Hz with `c = 0` and 68.885 Hz with fitted `c`. Numerical failures comprise three denied orbital extrapolations, two failed family-excluded phase convergences during cavity nomination and one assertion. The timeout reached the full 195-second limit. [Candidate and original metrics](summary.json)

| Method | Fixes per arm | Numerical failures | Timeouts | `c = 0` median / P95 (km) | Fitted `c` median / P95 (km) |
|---|---:|---:|---:|---:|---:|
| Compact secant | 16 | 6 | 1 | 1.062 / 5.348 | 1.156 / 5.330 |
| Original no-repair v5 | 13 | 9 | 1 | 0.818 / 2.846 | 0.739 / 2.823 |
| Original selective-gap | 11 | 11 | 1 | 0.798 / 2.001 | 0.739 / 2.006 |
| Original omitted-track-one | 8 | 10 | 5 | 0.717 / 2.619 | 0.705 / 2.587 |
| Original omitted-tracks | 5 | 9 | 9 | 0.917 / 3.934 | 1.003 / 3.924 |

The compact solver returned four fixes where original no-repair had none. Three original executions failed (DS26-0034, DS26-0160 and DS26-0251) and DS26-0221 timed out. The compact run timed out on DS26-0217, which original no-repair fixed. Among the 12 cases both fixed, median errors were 0.865 / 0.873 km for compact and 0.867 / 0.871 km for original no-repair. The largest compact errors, 6.695 / 6.736 km, were on DS26-0251, one of the newly recovered cases. [Per-recording comparison](scores.csv)

## Reproduce

Run from a new local workspace with the authenticated original capture-era files mounted. Prepare starts the shared deadline after verifying the exact input roster. Start one lane per granted CPU during that window. The example uses CPU 15 and the same worker cap as the measured run.

```bash
work=/tmp/compact-roof-complement
nice -n 10 .venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_selection \
  prepare --work "$work" --out "$work/report"
nice -n 10 taskset -c 15 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.compact_roof_selection lane --cpu 15 --work "$work"
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_selection_results \
  seal --work "$work" --out "$work/report"
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_selection_results \
  score --out "$work/report"
```
