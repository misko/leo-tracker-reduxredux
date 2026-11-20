# Native agreement with lazy compact fallback

The **0.5 km gate returned one fast fix in 135 roof recordings**. Both native methods published that recording and agreed across both calibration arms. The selected smooth-clock fix was still about a kilometre from the measured site. The full-panel serial work model increased elapsed work by **6.50%** over compact secant alone. Two live cases verified that the cascade skips compact on agreement and calls it only after disagreement. [Two-arm figure gallery](charts/index.html) · [Protocol](PROTOCOL.md) · [Sealed route decisions](routing.json)

## Common roof panel

The 127 DS26 and eight DS29 cases use the original supplied 25 km tile, native factors and causal catalogue. The three native digests for the request, archive and rebuilt Graph match between the smooth-clock and independent curve-anchor runs. The compact control binds the same recording, catalogue and tile through its original v5 request and source seal. Both arms travel together. The 100 disagreements and 34 native publication shortages delegated both arms to compact. Routing uses published positions and opens the score references after committing the route. [Source ledger](sources.json) · [Chart definitions](figures.json)

| Receiver | Published per arm | Median / P95 at `c=0` (km) | Median / P95 with fitted `c` (km) | Within 10% of paired original v5, `c=0` / fitted |
| --- | ---: | ---: | ---: | ---: |
| Compact secant | 135/135 | 0.977 / 2.936 | 0.989 / 2.817 | 131 / 131 |
| Native agreement cascade | 135/135 | 0.984 / 2.936 | 1.004 / 2.817 | 130 / 130 |
| Smooth clock | 119/135 | 1.530 / 4.463 | 1.284 / 4.751 | 40 / 47 |
| Curve anchors | 108/135 | 1.800 / 4.810 | 1.579 / 4.530 | 33 / 34 |

The percentile columns include published fixes. Paired thresholds count all 135 attempts, with a success requiring a coordinate and error at most 1.10 times the original no-repair v5 error on the same recording and arm. Conditional frequency RMS is a separate CSV field. The accepted DS26-0110 pair agreed to 0.472/0.487 km. Its published smooth-clock errors were 1.411/1.085 km, while compact achieved 0.097/0.071 km from the same recording and tile. [Case errors and RF RMS](errors.csv)

## Time and dependency cost

| Agreement ceiling in both arms | Fast / 135 | Modeled serial wall vs compact | Within 10% of paired original v5, `c=0` / fitted |
| --- | ---: | ---: | ---: |
| 0.25 km, descriptive | 0 | +7.20% | 131 / 131 |
| 0.50 km, primary | 1 | +6.50% | 130 / 130 |
| 1.00 km, descriptive | 26 | −9.62% | 118 / 119 |

The full panel adds the two measured native worker intervals for every recording and the same-record compact interval for the 134 fallback decisions. This is a serial-work model from separate sealed host runs, including the six earlier timing cases and eight earlier compact confirmations. The modeled sum is 19,448.8 s versus 18,262.6 s compact-only. Median modeled wall is 137.41 s versus 127.79 s, and the largest modeled case is 405.04 s versus 390.79 s. The two native checks add 1,314.4 s of measured wall and 1,204.1 s of measured worker CPU across the panel. The only accepted case avoids 128.4 s of archived compact wall. Historical compact CPU is unavailable, so the model omits a whole-panel CPU total. The 1.0 km sensitivity saves modeled time and loses more paired accuracy. [Timing and threshold sensitivity](summary.json)

The live fast branch requires both sandboxed native solvers and their Graph and orbit dependencies. The fallback retains both of those stages and adds the complete frozen v5 runtime, its causal archive and the compiled secant projector. In serial the worst route is `T_smooth + T_anchors + T_compact`. Each native check reads the complete archive and rebuilds Graph independently. The native sandboxes each enforce 512 MiB virtual address space. The compact branch retains its own runtime and deadline. The cascade has no measured global memory cap.

| Real native-start case | Calls | Wall | Accounted CPU | Compact interval |
| --- | --- | ---: | ---: | ---: |
| DS26-0110, CPU 5 | Smooth clock, anchors | 8.33 s | 7.96 s | None |
| DS26-0002, CPU 4 | Smooth clock, anchors, compact | 55.86 s | 54.97 s | 48.81 s |
| DS26-0110 independent compact control, CPU 5 | Compact | 59.47 s | 58.65 s | 59.47 s |

The CPU accounting combines process and waited-child CPU with the scientific worker CPU reported from each Bubblewrap PID namespace. Compact-only timing starts at binding the existing compact request on the already located native inputs. The two fresh compact controls reproduced their sealed positions exactly and retained both calibration arms. The fallback case's compact interval is the actual selected stage. The fast case's compact control is a separate invocation. [Complete live call receipts](fresh-receipts.json) · [Live accuracy rows](fresh-errors.csv)

## Wrong offers

Both native solvers ran on ten previously sealed tiles placing the site 1–2 km outside, ten placing it 6 km outside, and nine historical omitted offers. At 0.5 km the gate accepted none. Each native receiver published one 1–2 km wrong offer and two 6 km wrong offers on its own. All 29 routed compact outcomes are **unmeasured**. The trusted original-tile compact worker has no supported shifted-tile route. These tests measure rejection by the fast gate on the recorded wrong offers and leave arbitrary-region fallback accuracy open. [Shifted offers](shifted-omitted-queries.json) · [Archived omitted offers](archived-omitted-queries.json)

## Reproduction

The commands use the existing archived-factor environment, the native-lean deployed source bundle and the frozen compact numerical runtime. The report can be regenerated from the sealed exports and the two measured live directories.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
scratch=$(mktemp -d /tmp/native-cascade.XXXXXX)
taskset -c 5 .venv/bin/python -B -m tools.pipeline_eval.qualification.native_agreement_cascade_fresh \
  --id DS26-0110 --cpu 5 --work "$scratch/fast" --control
taskset -c 4 .venv/bin/python -B -m tools.pipeline_eval.qualification.native_agreement_cascade_fresh \
  --id DS26-0002 --cpu 4 --work "$scratch/fallback"
.venv/bin/python -B -m tools.pipeline_eval.qualification.native_agreement_cascade_eval \
  --out "$scratch/evidence" --fresh "$scratch/fast" "$scratch/fallback"
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --variant native_agreement_cascade --evidence "$scratch/evidence" --out "$scratch/charts"
```
