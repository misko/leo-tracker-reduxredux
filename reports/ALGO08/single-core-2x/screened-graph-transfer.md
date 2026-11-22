# Guarded graph solver on the second roof recording and the distant omitted region

On DS30-0008, the frozen graph solver reproduced the deployed fix exactly on deployed detections. Switching to the candidate detections increased horizontal error by **19.09 m with fixed-zero calibration and 18.89 m with fitted calibration**. The solver also correctly withheld on the southern African simulation when truth was 57.03 km beyond the offered region. These are three saved solves. They include a second roof recording and an off-site simulation, with no new raw recordings or hidden inputs.

| DS30-0008 solver and receiver measurements | Returned observations per arm | Horizontal error, fixed-zero / fitted | Frequency RMS, fixed-zero / fitted |
|---|---:|---:|---:|
| Deployed solver, deployed measurements | 4,472 | 1.639 / 1.512 km | 129.703 / 129.663 Hz |
| Guarded graph solver, deployed measurements | 4,472 | 1.639 / 1.512 km | 129.703 / 129.663 Hz |
| Guarded graph solver, candidate measurements | 4,470 | 1.658 / 1.531 km | 129.752 / 129.711 Hz |

The deployed-measurement crossover took 55.53 CPU seconds and matched both deployed coordinates, owner hashes and residuals exactly. The candidate-measurement solve took 61.58 CPU seconds. Both had 7,016 selected measurements at the same opportunities and ranks. Three primary carrier estimates changed by up to 17.63 microhertz. Earlier testing localized a change in track membership to two nearly tied polynomial proposals. Small input changes can therefore affect which observations reach the final position fit. The previous covariance solver scored 1.331 / 1.308 km on the same candidate measurements and lost accuracy on the southern African containing case. The stronger roof score alone was insufficient to select that solver. [Candidate measurements](measurements/screened-graph-dense.json) · [Deployed-measurement crossover](measurements/screened-graph-dense-deployed.json) · [Track arbitration](graph-native-path.md#source-of-the-dense-membership-change) · [Southern transfer](portable-south-solver-attribution.md)

For the distant southern omission, the deployed solver issued two fixes 89.79 km from truth. The guarded graph solver withheld both with reason `both_receivers_support_far_exterior` in 59.32 CPU seconds. The prior screened recovery withheld on the same offer in 89.59 CPU seconds with extra tracing. Each clock is one observation. The distant result and the earlier Indian false fix at 1.5 km outside are separate operational cases. [Southern omission](measurements/screened-graph-south-far.json) · [India omission](screened-tiled-publication.md#evidence-by-solver-version)

## Frozen checks

Use the existing native-graph build `e279026b` on two saved detection documents before scheduling another raw recording. DS30-0008 is second in the original roof order and previously exposed an accuracy loss from approximate initial ranking. Compare the two returned positions, frequency residuals and owner hashes against the deployed raw publication on the same recording. Its deployed receiver produced its own detections. Also compare with the archived covariance solver that consumed the identical candidate detector document. Score both calibration arms against the operator reference only after inference.

The second input is the released southern African portable simulation with the original distant omitted square. Reuse its saved detections and causal catalogue as frozen. Record whether the guarded graph solver still withholds and its stated reason. Compare with the installed solver and earlier screened recovery on those same detections. Neither input supplies a new location for blind confirmation. The timers cover saved detections through the solver's selected evidence packet.

## Reproduction

Run from the research checkout in its Python environment, choosing a new output filename for each invocation. The initial plan was frozen at `e40e9f6cb`. The additional deployed-measurement crossover was run after the candidate-measurement result showed a loss.

```sh
bench=/tmp/leo-algo08v2-2x-bench
pair=/tmp/ds30-v2-stage-covariance-375895/DS30-0008/pair.json
py=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
replay() {
  flock "$bench/gauss.lock" nice -n15 ionice -c2 -n7 taskset -c 2 \
    env PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    "$py" -BPs -m reports.ALGO08.single-core-2x.screened_graph_transfer "$@"
}
replay dense "$bench" "$bench/dense-next.json" --pair "$pair"
replay omitted "$bench" "$bench/far-next.json"
replay dense "$bench" "$bench/dense-deployed-next.json" --pair "$pair" --deployed-detections
```
