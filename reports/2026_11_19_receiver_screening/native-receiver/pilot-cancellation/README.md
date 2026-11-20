# Qin pilot cancellation on saved stereo I/Q

Training-only subtraction exposed the weaker injected pilot on both Qin edges. On 42 saved visits, subtraction recovered **zero missed original winners** and produced no literal second pilot beyond the equal-width retry on raw samples. The chief coverage loss was timing nomination. For the 21 lanes with an admitted primary, subtracting the predicted wave increased held coherent power on 15. These results are for the acquisition stage. Position accuracy is unmeasured. [Protocol](PROTOCOL.md) · [Chart](stage.png) · [Plotted values](stage.csv)

## Coverage and host cost

The roster contains 30 gate-balanced visits and 12 separately drawn collision witnesses across three installed producers and both Qin edges. The installed detector reproduced all 36 valid dual-receiver packets and all six invalid capture records. The table counts original winning lanes within each cohort. A literal match is within two samples circularly and 1 kHz in signed CFO. Duplicate ranks and OFDM CFO aliases do not add literal matches.

| Detector stage | Systematic winners, 24 positive lanes | Targeted winners, 19 positive lanes | Literal follow-ups, systematic / targeted | CPU ms per valid visit, median [range] |
| --- | ---: | ---: | ---: | ---: |
| Installed GLRT | 24 | 19 | | 2,182 [963–4,174] |
| Primary four-center search | 11 | 8 | 0 / 0 | 99 [81–129] |
| Four-center retry on raw samples | 11 | 9 | 1 / 1 | 123 [84–205] |
| Twelve-center raw search | 11 | 9 | 0 / 3 | 264 [219–339] |
| Four-center cancellation retry | 11 | 8 | 1 / 0 | 128 [85–230] |

Each valid visit had five rotating measured repetitions after one warm pass per arm. There were zero unstable payloads across 1,050 measured calls including the invalid captures. CPU starts at resident CI16 and includes both lanes, the capture check, and candidate or original packet construction. The experimental primary spends most of its time fitting literal CFO at shortlisted epochs. At the similar CPU cost of the two four-center retries, subtraction lost one targeted winner and retained the same one uncorroborated systematic follow-up. The wide baseline recovered a different targeted winner. The primary missed 24 winners. Of those, 22 were outside its searched timing cells, one failed the held gate, and one ranked behind an admitted alternative. [Lane detail](lanes.csv) · [Every measured repeat](timings.csv) · [Qualification](qualification.json)

## Which visits had two pilots

- **DS26-0237 visit 435, receiver 0.** Both fixed candidates had Qin support in all four common held blocks and literal archive matches. The no-subtraction, shifted, and phase-shuffled retries found the same second family. Cancellation increased the primary coherent projection by about 4%. The second pilot was present before subtraction.
- **DS29-0519 visit 298, receiver 0.** The new candidate had exact-versus-rolled support alongside the primary in all four blocks. It lacks a literal or alias match in the original pass list and also appeared with no subtraction and shifted subtraction. This is waveform evidence for an uncorroborated candidate.
- **DS26-0237 visit 659 and DS29-0519 visit 170, both receiver 0.** In each case, the four-center primary had simultaneous support with the original winner it missed. The wide raw arm recovered the former. The equal-width raw retry and shuffle recovered the latter. Cancellation recovered neither.

The post-prediction check supported nine of ten tested targeted archive pairs. It projected each candidate orthogonal to the other on the same raw held blocks. Both injected simultaneous pairs passed. The single-pilot and sequential injections failed on both edges. Each result is a statement about the sampled lane and fixed CFOs. Receiver-to-receiver identity and satellite association were outside this stage. [Overlap method](OVERLAP.md) · [Block measurements](overlap.json.gz)

## Why the injection and recording results differ

The injected pilots had stable complex gains and carrier frequencies. Cancellation recovered both planted literal coordinates on both edges, removed over 95% of the primary held coherent power, and emitted no second in the strong-only, noise, or zero controls. On the saved visits, the median absolute phase error of the trained gain was 1.35 rad and the held-to-predicted amplitude ratio was 0.84. At fixed energy, the primary coherent power after cancellation was 2.99 times the original at the median. After normalizing by each residual's energy, median power removed was 0% without subtraction, 2% with shifted subtraction, −46% with shuffled subtraction, and −194% with aligned subtraction. Wrong-edge, opposite-CFO, and zero-CFO comparisons failed the held coded gate on all 21 measured primaries. The failed transfer leaves little reason to add this subtraction to a passive locator, even on lanes with real simultaneous pilots. [Synthetic controls](controls.json.gz) · [Case predictions and authority](prediction-lock.json)

## Reproduce the stage

From the repository root, choose a new local output directory. The replay uses the existing capture archives and installed production analyzers.

```bash
out=$(mktemp -d /var/tmp/leo-pilot-cancellation-XXXXXX)
export PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
taskset -c 12,13 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_cancellation_trial freeze "$out"
taskset -c 12,13 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_cancellation_trial run "$out"
taskset -c 13 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_cancellation_overlap "$out"
taskset -c 13 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_cancellation_results "$out"
taskset -c 13 .venv/bin/pytest -q tests/pipeline_eval/test_pilot_cancellation.py
```

The sealed standard v1 descriptor references the PNG, PDF, and CSV. Each of the 42 source rows retains its original status, raw digest, and full replay packets or excluded-capture record. [Descriptor](stage-figure.json) · [Evidence seal](stage-figure-lock.json)
