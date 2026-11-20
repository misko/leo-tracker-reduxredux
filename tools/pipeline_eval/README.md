# Run the receiver benchmark

To check conditional antenna acquisition on the eight discovery recordings, the 14-recording holdout and two additional complete saved-I/Q recordings, use the command below. It reports matched 5% and 10% position counts, both RF calibration settings, paired effects and measured runtime. Open `OUT/charts/index.html` to browse seven position comparisons. Both calibration folders contain the PNGs, a PDF book and `modifications.csv` point data. [Cohorts, error distributions and timing](../../reports/2026_11_19_receiver_screening/antenna-confirmation/benchmark/README.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver antenna-confirmation --out /tmp/antenna-confirmation
```

To compare the accuracy and cost of retaining original GLRT factors, use the original-support benchmark. It writes a browsable position gallery and point data for both calibration settings, scoped error and RF tables, and separate tables for actual and modeled queue admissions. [Original-support evidence and benchmarks](../../reports/2026_11_19_receiver_screening/original-support/benchmark/README.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver original-support --out /var/tmp/original-support
```

Any receiver study that publishes a sealed `figures.json` can use the same command to regenerate its position distributions. It writes individual figures, two calibration books, a browsable index, and a CSV of scheduled, published, withheld and unavailable results. Each roof recording is compared to its original v5 error at 5% and 10%. Region offers retain their individual conditions. This example tests the rule that reads the other antenna when the first misses the pilot.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study reports/2026_11_19_receiver_screening/pilot-influence/second-on-miss-roster \
  --out /tmp/second-on-miss
```

To compare one physical antenna per visit with the four-region, five-region and alternating-fifth receivers on the same 22 recordings, run the command below. It regenerates the position distributions, the table of individual errors and a chart joining each measured replay time to its position accuracy on that recording. Two complete one-antenna waveform runs also check the independent antenna projection. [Accuracy and timing benchmark](../../reports/2026_11_19_receiver_screening/pilot-influence/one-lane-benchmark/README.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver one-lane --out /tmp/one-lane-benchmark
```

To compare a fifth timing search alternating between the two antennas with fixed four, fixed five and the four original v5 policies, use the command below. It regenerates the position-error distributions, measurement scopes and times for 22 recordings, including the separate two-recording full-I/Q holdout. [Staggered benchmark and individual errors](../../reports/2026_11_19_receiver_screening/receiver-choice/staggered-benchmark/README.md) · [Modification gallery](../../reports/2026_11_19_receiver_screening/receiver-choice/index.html)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver staggered --out /tmp/staggered-benchmark
```

The complete-recording benchmark compares the four- and five-region detectors on twenty scheduled saved I/Q recordings. It checks the duplicate stock outcomes and the raw recording, catalogue, request and executable identities. Its summary includes the four original v5 policies, geographic errors in both calibration settings, individual paired differences and the sensitivity to an earlier stock timeout. It also exports per-recording elapsed times and 20 ms detector deadline counts, using timing receipts matched to the native outputs and position results. The offline command below uses the measured results included with the checkout. [Benchmark protocol and outputs](../../reports/2026_11_19_receiver_screening/latency-and-support/complete-roster/README.md) · [All changes in this round](../../reports/2026_11_19_receiver_screening/latency-and-support/index.html)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --out /tmp/complete-detector-roster
```

The arrival-time benchmark includes new complete roof recordings, a detector test on a UT Austin waveform, and real-time host replays that score the position from the visits the receiver actually processed. Build its offline collection or request a single comparison from the same evidence. The commands below run from the checkout. [Study results](../../reports/2026_11_19_receiver_screening/arrival-and-timing/README.md) · [Chart index](../../reports/2026_11_19_receiver_screening/arrival-and-timing/index.html)

```sh
study=reports/2026_11_19_receiver_screening/arrival-and-timing
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack --evidence "$study"
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence "$study" --variant buffered-position-fifth --arm both --out /tmp/fifth-region-buffer
```

To view or regenerate the comparison of four and five GLRT timing regions on the six complete waveforms, use the command below from the checkout. Each calibration arm has its own error distribution with the original v5 reference options on the same recordings. The study guide also gives the command for every measured modification and stage in one offline ZIP. [Six-recording comparison](../../reports/2026_11_19_receiver_screening/support-preserving/fifth-crossover/README.md) · [Gallery commands](../../reports/2026_11_19_receiver_screening/support-preserving/GALLERY.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/support-preserving \
  --variant fifth-center-all-six --arm both --out /tmp/fifth-center-comparison
```

To reproduce the earlier GLRT pilot-timing comparisons from their saved evidence, run the command below. It creates one error distribution per measured position comparison in each calibration setting, the measured detector-stage figures, the per-recording rows and an offline ZIP. The held and development recordings also have independent charts. [Gallery](../../reports/2026_11_19_receiver_screening/acquisition-frontier/index.html) · [Test rosters and results](../../reports/2026_11_19_receiver_screening/acquisition-frontier/README.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence reports/2026_11_19_receiver_screening/acquisition-frontier
```

To regenerate the pilot-recovery comparison from its recorded results, run this command from the checkout. It writes `index.html`, individual PNGs, the per-recording tables and a ZIP that opens offline. Both calibration settings have position-error charts. Detector-only changes have stage figures showing their actual measured outputs. [Study results](../../reports/2026_11_19_receiver_screening/track-recovery/README.md) · [Browse the charts](../../reports/2026_11_19_receiver_screening/track-recovery/index.html)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence reports/2026_11_19_receiver_screening/track-recovery
```

Build the stock wide GLRT and adjacent-sample variant locally with `python3 -m tools.pipeline_eval.wide_runtime --out /var/tmp/leo-wide-local`. The standard-library builder uses a frozen source capsule, GCC, GNU binutils and FFTW development files. The output includes the library digests used by the complete-I/Q benchmark. [Portable build, dependencies and verification](../../reports/2026_11_19_receiver_screening/track-recovery/wide-release/README.md)

The receiver-core benchmark compares the fast detector against original v5 on the same factors, through full saved I/Q, and on held geographic offers. To regenerate its individual error distributions from the sealed results, run the first command. The second command creates an offline index with a stage figure or a position-error figure for each evaluated modification. [Individual charts](../../reports/2026_11_19_receiver_screening/receiver-core/index.html) · [Results and per-study replay commands](../../reports/2026_11_19_receiver_screening/receiver-core/README.md)

```sh
evidence=reports/2026_11_19_receiver_screening/receiver-core
.venv/bin/python -m tools.pipeline_eval figures --panel screening --evidence "$evidence" --out "$evidence/charts"
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack
```

To regenerate one position-error chart per tested acquisition or receiver change, run the following from the repository root. The output contains fitted-`c` and `c = 0` PNGs, PDF books, and the recording-level values behind each dot. The gallery includes the four original v5 options when they were run on the same recordings. The title and dot counts identify the actual test roster. [Chart index](../../reports/2026_11_19_receiver_screening/acquisition-support/index.html) · [Original ten modifications](../../reports/2026_11_19_position_atlas/original-ten.html)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/acquisition-support \
  --out /tmp/receiver-change-charts
```

For the [portable set of individual PNGs](../../reports/2026_11_19_receiver_screening/acquisition-support/modification-charts.zip), run `.venv/bin/python -m tools.pipeline_eval.qualification.acquisition_pack --out /tmp/modification-charts.zip`. The ZIP combines the published figures, detector-stage pages and per-recording data from this checkout, with an index that opens offline.

To benchmark a new GLRT library from recorded I/Q through both position fits, use a study specification like the [eight-recording pilot trial](../../reports/2026_11_19_receiver_screening/acquisition-support/scout-full/study.json). Specify each library's SHA-256, the recording IDs, two available cores per pair, which library goes first, and the whole-recording deadline. The commands below require the recording archive host for preparation and replay. Supply local paths for the study, both detector libraries and the installed receiver. Use new work and report directories.

```sh
.venv/bin/python -m tools.pipeline_eval.iq_compare prepare \
  --spec "$STUDY/study.json" --protocol "$STUDY/PROTOCOL.md" \
  --receiver "$RECEIVER" --control "$CONTROL_LIBRARY" --candidate "$CANDIDATE_LIBRARY" \
  --work "$WORK"
for case_id in $(.venv/bin/python -c 'import json,sys; print(*json.load(open(sys.argv[1]))["cases"])' "$WORK/source-lock.json"); do
  .venv/bin/python -m tools.pipeline_eval.iq_compare run --work "$WORK" --case "$case_id" || break
done
.venv/bin/python -m tools.pipeline_eval.iq_compare seal --work "$WORK" --out "$REPORT" --keep-factors
.venv/bin/python -m tools.pipeline_eval.iq_compare publish --out "$REPORT"
```

`seal` checks both attempts for every recording and freezes predictions, including failures, before `publish` opens the survey and v5 references. Passing `--keep-factors` also preserves the completed detector outputs for downstream experiments. The release checks the saved I/Q, clock, invalid visits, detector libraries, position program and causal orbit archive. Each pair has the same 512 MiB memory allowance and zero swap. A failed position can still have a complete, verifiable detector output.

If the host or its service monitor is interrupted, repeat the same `run --work "$WORK" --case "$case_id"` command. It checks the existing service log and terminal state before dispatching the next detector. To inspect one interrupted attempt directly, run `.venv/bin/python -m tools.pipeline_eval.iq_service recover "$WORK/$case_id/control"`. The receipt identifies the service clock and any unavailable supervisor measurements. The [deadline audit](../../reports/2026_11_19_receiver_screening/acquisition-support/deadline-repeat/README.md) includes the original timeouts and an independently scored repeat.

Build the standalone stored-GLRT receiver with `.venv/bin/python -m tools.pipeline_eval.cavity_runtime /tmp/leo-cavity`, then run `.venv/bin/python -IB /tmp/leo-cavity --help` for its orbit, recording and region inputs. The installer also accepts `--profile majority` and `--profile longitude` for the independently measured support rule and date-line geometry. [Build, use and measured limits](../../reports/2026_11_19_receiver_screening/next/cavity-payload/README.md) · [Matched pipeline and transfer charts](../../reports/2026_11_19_receiver_screening/next/charts/index.html)

The `--profile phase-release` option releases each constrained position model after its last use. On DS29-0247 it returned the same numerical output under 512 MiB as the original solver with a larger memory allowance. The full stored-IQ replay also finished under the 512 MiB limit. [Complete-IQ chart and stage times](../../reports/2026_11_19_receiver_screening/detector-origins/whole-pressure/README.md) · [Memory measurements](../../reports/2026_11_19_receiver_screening/detector-origins/pressure/README.md)

To withhold a fix when either calibration estimate lands within 20 m of the fitted region edge, install the `interior` profile. It applies the rule after the position solve and includes the withheld coordinates in the result for diagnosis. On two roof recordings the rule suppressed four incorrect region publications and one of two legitimate publications. [Measured tradeoff](../../reports/2026_11_19_receiver_screening/receiver-core/measured-boundary-policy/README.md) · [Standalone entry and parity checks](../../reports/2026_11_19_receiver_screening/receiver-core/installed-interior/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.cavity_runtime /tmp/leo-interior --profile interior
.venv/bin/python -IB /tmp/leo-interior --help
```

Open the position distributions for the [ten original modifications](../../reports/2026_11_19_position_atlas/original-ten.html), the [latest recovery experiments](../../reports/2026_11_19_receiver_screening/recovery/charts/index.html), or the [full position atlas](../../reports/2026_11_19_position_atlas/index.html). To regenerate the ten charts from the sealed per-recording predictions, run the command below and open its `index.html`. The two ten-page PDF books, the individual PNGs and the data for each dot are included. Both calibration arms use the same recordings.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel matched135 --out /tmp/receiver-ten
```

To rebuild the full-IQ detector comparisons, the position-only changes and the held-region charts from their sealed predictions, run the same chart generator on the study directory. It writes a PDF book per calibration, individual PNGs and the data for every dot. [Current charts](../../reports/2026_11_19_receiver_screening/detector-origins/charts/index.html) · [Study and sample counts](../../reports/2026_11_19_receiver_screening/detector-origins/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/detector-origins \
  --out /tmp/detector-position-charts
```

Use `whole_iq` to evaluate a native short-window GLRT library through the installed compact position program on an entire stored recording. Supply the library's release SHA-256 and two available cores. On the archive host the capture-specific reader runs under the existing `leo` account via `sudo -n -u leo`, and the user systemd manager enforces 512 MiB, zero swap and the elapsed deadline. Both receivers use the actual IQ and causal TLEs. Each attempt directory must be new. A completed raw stage has its own receipt even when positioning fails. [Bounded six-recording schedule](../../reports/2026_11_19_receiver_screening/detector-origins/whole-band/PROTOCOL.md) · [Position and RF results](../../reports/2026_11_19_receiver_screening/detector-origins/whole-band/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.cavity_runtime /tmp/leo-cavity
.venv/bin/python -m tools.pipeline_eval.whole_iq run --case DS29-0082 \
  --detector "$DETECTOR_LIBRARY" --detector-sha256 "$DETECTOR_SHA256" \
  --receiver /tmp/leo-cavity --cpus 0 1 --limit-s 360 --out /tmp/iq-ds29-0082
```

Run these commands from the repository root with the project Python environment. The first prints the frozen v5 comparison in both calibration arms. The second runs a live regional receiver on eight acquisitions, each with a correct-region-present and a correct-region-missing query. Both work on a checkout without external radio archives.

```sh
.venv/bin/python -m tools.pipeline_eval
.venv/bin/python -m tools.pipeline_eval run --variant orbit_interp --panel transfer16 --jobs 4 --require-inputs
```

These three commands evaluate all registered modules on the 16 recordings and compare their results.

```sh
OUT=/tmp/receiver-benchmark
.venv/bin/python -m tools.pipeline_eval run --variant all --panel roof16 --jobs 4 --pin --out "$OUT"
.venv/bin/python -m tools.pipeline_eval compare --panel roof16 --out "$OUT"
.venv/bin/python -m tools.pipeline_eval plot --panel roof16 --out "$OUT"
```

The native v5 worker takes minutes per recording. The default is one numerical thread per worker and a 1,200-second per-case deadline. `--jobs` limits the number of concurrent workers. Hashing input archives, preparing the observation cache and starting the command take additional time. `--pin` restricts each numerical worker to one available CPU. Use `--require-inputs` to fail the command if any requested input is unavailable. Every result includes its input boundary. Paired timings describe the two implementations on identical inputs within that boundary. The wall time around the worker includes both sides when a module runs a fresh control.

`v5_armijo_finish` applies Armijo fitting through the final compact v5 decision. `v5_discovery_memory` reuses one association during discovery and stops at the compact secant cavity decision. Standard roof runs bind each method to the published capture-era native factors, the causal TLE history and the original tile. The working-memory qualification also binds complete ordinary native replays in separate comparisons. [Armijo finish protocol](../../reports/2026_11_19_receiver_screening/armijo-finish/PROTOCOL.md) · [Working-memory protocol](../../reports/2026_11_19_receiver_screening/working-memory/PROTOCOL.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS29-0082 \
  --variant v5_armijo_finish --variant v5_discovery_memory --pin --out /tmp/compact-v5
```

`v5_armijo_aligned_finish` runs the same final selection with a guarded alignment of the incoming phase seed to the ordered candidate catalogue. Run both Armijo variants on the phase-slot stress recording with the original native factors and roof tile. The command scores both calibration arms. [Four-recording regression protocol](../../reports/2026_11_19_receiver_screening/armijo-finish/aligned/PROTOCOL.md) · [Original Armijo study](../../reports/2026_11_19_receiver_screening/armijo-finish/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0066 \
  --variant v5_armijo_finish --variant v5_armijo_aligned_finish --pin --out /tmp/armijo-alignment
```

The final-stage experiments use the same published roof inputs. `v5_pruned_finish` checks residual time folds and family support before expensive evaluations. `v5_stream_recovery` retains the aligned finish and reads late orbital geometry in bounded groups from local scratch. `v5_screened_pruned_finish` shares initial discovery work, screens assignments and runs the pruned aligned finish. `v5_armijo_tail` runs through the compact cavity and checks small Armijo steps with at most two symmetric linearizations. [Original pruning denominator](../../reports/2026_11_19_receiver_screening/inference/pruned-finish/audit/README.md) · [Recovery memory trial](../../reports/2026_11_19_receiver_screening/inference/stream-recovery/README.md) · [Integrated finish protocol](../../reports/2026_11_19_receiver_screening/inference/screened-pruned/PROTOCOL.md) · [Armijo tail trial](../../reports/2026_11_19_receiver_screening/inference/solver-tail/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0066 \
  --variant v5_armijo_aligned_finish --variant v5_pruned_finish \
  --variant v5_stream_recovery --pin --out /tmp/receiver-finish
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0175 \
  --variant v5_screened_pruned_finish --pin --out /tmp/receiver-integrated
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0313 \
  --variant v5_armijo_tail --pin --out /tmp/receiver-tail
```

`joint_orbits` starts from prepared anonymous tracks and their causal TLE snapshot with one supplied tile. The normal benchmark records both file digests and the tile in the prediction receipt. The archived omitted-region, shuffled and synthetic controls use the separate qualification driver. [Joint orbit assignment protocol](../../reports/2026_11_19_receiver_screening/inference/joint-orbits/PROTOCOL.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0261 \
  --variant joint_orbits --pin --out /tmp/joint-orbits
```

`portable_native_joint` and `portable_native_clock` start from complete native GLRT factors and rebuild Graph tracks before their position fit. The same receiver can run directly on local capture files and any supplied region. It emits both calibration arms, file and source digests, and worker timings in JSON. On prepared-only benchmark cases the native variants report unavailable. [Standalone command, bundle and replay parity](../../reports/2026_11_19_receiver_screening/refinement/portable-worker/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS26-0036 \
  --variant portable_native_joint --pin --timeout 60 --require-inputs --out /tmp/native-joint
.venv/bin/python -m tools.pipeline_eval.variants.lean_receiver_cli solve --help
```

`v5_recovery_bank_reuse` runs the complete compact v5 fit on the stored native GLRT factors, causal catalogue and original roof tile. It reuses the validated residual orbit bank during final reassociation and keeps the independent propagation audit. The benchmark writes scores and position-error figures for both calibration arms. [Paired measurements and chart data](../../reports/2026_11_19_receiver_screening/factors/v5-reuse/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS29-0082 \
  --variant v5_recovery_bank_reuse --pin --timeout 480 --require-inputs --require-v5 \
  --out /tmp/receiver-bank-reuse
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --variant v5_recovery_bank_reuse --out /tmp/receiver-bank-reuse-figures
```

## Get one position-error figure per modification

To read a curve at a fixed fraction of **all offered recordings**, use the coverage command. It reports the error needed to cover 50%, 75%, 90% and 95%, paired counts within 5% and 10% of original v5, gains and losses of fixes, and false publications on missing-region offers. A `null` radius means the receiver published too few positions to reach that coverage. Omitted predictions count in the selected panel. Pass explicit `--case` arguments when evaluating a subset. This example reproduces the full DS26 result from the saved predictions.

```sh
.venv/bin/python -m tools.pipeline_eval coverage --panel ds26-all159 \
  --predictions reports/2026_11_19_receiver_screening/integration/failed-only/all159-replay.jsonl.gz
```

The streamlined studies include archive-to-position replays, a distributable compact position worker, interleaved IQ visits, held orbit identities and blind region edges. [Charts](../../reports/2026_11_19_receiver_screening/streamlined/charts/index.html) · [Evidence for each change](../../reports/2026_11_19_receiver_screening/streamlined/README.md)

The integration gallery includes the full 159-recording DS26 comparison, 512 MiB replays from both saved IQ and stored detector outputs, held-out region edges and detector changes. Rebuild its two calibration books and per-recording CSVs directly from the sealed evidence. [Gallery](../../reports/2026_11_19_receiver_screening/integration/charts/index.html) · [Per-modification evidence](../../reports/2026_11_19_receiver_screening/integration/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/integration --out /tmp/integration-charts
```

Each new roof `run` already writes `position-errors-fitted_c.png` and `position-errors-c0.png` alongside its `predictions.jsonl` and `errors.csv`. A run limited by `--case` puts those files in the method's `subset-…` directory. For the saved experiments, the commands below rebuild the individual charts and their books without replaying the radio data. Use **Find a modification** in a multi-chart gallery to filter by title or method name.

The [original ten charts](../../reports/2026_11_19_position_atlas/original-ten.html) use the same 127 DS26 and eight DS29 recordings as the first comparison. The [redesign charts](../../reports/2026_11_19_receiver_screening/redesign/charts/index.html) include the full DS26 roster, the 32 recordings excluded from the original comparison, and the geographic and runtime trials. Select a calibration setting to see each modification's cumulative distribution and individual errors.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/redesign --out /tmp/redesign-charts
.venv/bin/python -m tools.pipeline_eval baseline --panel ds26-excluded32
```

The [deployment gallery](../../reports/2026_11_19_receiver_screening/deployment/charts/index.html) has 24 comparisons covering same-core timing, capped memory, orbital state repairs, direct GLRT fitting, publication deadlines and wrong-region tests. The first command rebuilds the charts using the sealed results. The second executes the 30-second post-GLRT policy on a stored capture and records the new position or withholding outcome in each arm. The other deadline choices are `deadline_90s` and `deadline_180s`. [Inputs, sample counts and results](../../reports/2026_11_19_receiver_screening/deployment/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/deployment --out /tmp/receiver-deployment
.venv/bin/python -m tools.pipeline_eval run --variant deadline_30s --case DS26-0036 \
  --out /tmp/receiver-live
```

For the original ten modifications on the same 127 DS26 and eight DS29 recordings, this command writes ten figures in each calibration arm and a gallery with a switch between them. [Fitted-calibration book](../../reports/2026_11_19_position_atlas/roof/fitted_c/original-ten.pdf) · [Zero-calibration book](../../reports/2026_11_19_position_atlas/roof/c0/original-ten.pdf)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel matched135 --out /tmp/ten-position-charts
```

To regenerate the complete gallery, run the command below and open `index.html` in its output directory. Each chart has a full-resolution PNG. The gallery includes the ten original pipeline changes, the later roof comparisons, the earlier prototype variants, and the location tests with the correct region offered or omitted. Use the radio buttons to switch between fitted calibration and `c = 0`. [Browse all comparisons](../../reports/2026_11_19_position_atlas/index.html)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel atlas --out /tmp/position-charts
```

The same gallery includes full and 180-second exposures, alternative initial assignments, fused GLRT refinement, new anonymous-track fits, and trials on independently measured and simulated sites. For those studies alone, use the command below. Add a variant such as `--variant v5_first_ranked` to export a single comparison. Each output has an `index.html`, full-resolution images, printable PDFs and the rows used to draw them. [Short receiver results](../../reports/2026_11_19_short_receiver/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel short-receiver --out /tmp/short-receiver-charts
```

For the phase budget, position solver, periodic detector, exact orbit fit and region challenges, select the convergence panel. The first command renders all measured comparisons in that panel. The second selects the phase-budget change and its independent confirmation recordings. Both commands read the saved predictions and include a separate chart book and per-case data for each calibration setting. [Convergence chart gallery](../../reports/2026_11_19_position_atlas/convergence/index.html) · [Measurements and processing times](../../reports/2026_11_19_receiver_convergence/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel convergence --out /tmp/receiver-convergence
.venv/bin/python -m tools.pipeline_eval figures --panel convergence --variant v5_two_refresh --out /tmp/two-refresh
```

The screening panel reads the saved experiments through each study's evidence manifest.
Use a method or chart ID with `--variant` to select one study. The complete atlas also
includes these charts. [Screening chart gallery](../../reports/2026_11_19_position_atlas/screening/index.html) · [Study manifest format](../../reports/2026_11_19_receiver_screening/FIGURES.md)
The embedded projector chart covers the two measured grids and leaves position unmeasured.
[Arm projector grid metrics](../../reports/2026_11_19_receiver_screening/embedded/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both --out /tmp/receiver-screening
.venv/bin/python -m tools.pipeline_eval figures --panel screening --variant v5_secant_fit-roof135 --out /tmp/secant-roof
```

The roof output also includes `paired-v5.csv`. Its 5% and 10% columns count recordings where both receivers returned a fix and the modification's horizontal error was at most 1.05 or 1.10 times the no-repair v5 error on that recording. The recording, publication, withholding and paired-fix counts give the denominators. Median and P95 use the modification's published fixes.

The first command builds one page per published modification, including the ten full-pipeline directions, the earlier DS26 prototypes and the cold-start receivers. The second rebuilds the ten directions with their smaller qualification panels. The third plots your own completed benchmark runs. Each writes individual PNGs, an illustrated gallery, a multipage PDF and the errors behind every dot for both calibration settings. [Browse the complete comparison](../../reports/2026_11_19_glrt_cold_start/figures/README.md) · [Whole-IQ qualification](../../reports/2026_11_19_receiver_frontend/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --out /tmp/all-receiver-figures
.venv/bin/python -m tools.pipeline_eval figures --additional --out /tmp/receiver-figures
.venv/bin/python -m tools.pipeline_eval figures --runs /tmp/receiver-benchmark --panel roof16 --out /tmp/my-figures
```

Seven receivers also ran on the complete geographic transfer panel. The following command plots each receiver alongside the original regional search. Every acquisition appears once with the correct region offered and once with it missing. A separate chart compares the longitude check and the arc receiver on 40 freshly generated acquisitions. [Geographic transfer figures](../../reports/2026_11_19_receiver_frontend/transfer-figures/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel transfer124 --out /tmp/receiver-transfer-charts
```

Every chart compares the candidate with all four v5 configurations on the same recording IDs. The ten full-pipeline directions use 127 DS26 and eight DS29 recordings. Other studies show their measured roster, including the early prototypes tested on eight DS26 recordings. The two calibration directories contain matched `fitted_c` and `c0` comparisons. Use `--variant orbit_interp` or `--arm fitted_c` for a narrower export. With `--additional`, a second book shows the smaller eight-plus-eight bench and the two full-recording native-GLRT-to-v5 replays. [Ten full-pipeline charts](../../reports/2026_11_18_pipeline_eval/figures/README.md)

The live variants `point_votes_global`, `rate_triplets_global` and `folded_doppler_global` start with GLRT peaks, acquisition timing and causal TLE data, with an Earth-wide search. Replace the suffix with `_matched_tile` to give the same solver the original v5 search tile. The benchmark records the native and catalogue hashes, the supplied prior when used, both calibration arms and any diagnostic best guess. For a stored comparison with both search modes on the same page, use the unsuffixed method name in the figure command. [Physics, assumptions and scored controls](../../reports/2026_11_19_glrt_cold_start/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval run --variant folded_doppler_global --panel smoke --out /tmp/glrt-start
.venv/bin/python -m tools.pipeline_eval figures --variant folded_doppler --out /tmp/folded-figures
```

Fresh `run`, `replay`, `full` and `score` commands also write `current/position-errors-fitted_c.png` and `current/position-errors-c0.png`. Roof panels use the four v5 controls. Transfer panels compare to the original regional search and show the actual query counts for each offer condition, including subsets. Plotting happens after receiver timing ends. A detector-only timing run labels position as unmeasured. The published figures for both original GLRT modifications use a dedicated downstream replay of 80 scheduled windows per recording.

The subsequent `v5_core` experiment compares five v5 stopping points on the same 135 recordings and runs a reduced position worker from native detections on six paired timing cases. Its two figure books, source rows and reproduction commands are in the [stopping-point report](../../reports/2026_11_19_receiver_simplification/README.md).

To regenerate the additional measurements on the corpus host, run these commands from the repository root, using a local output directory. The region file preserves the original DS26 distractors and the DS29 blind offers with matching observation and catalogue digests. The 16-recording front-end run also reruns both unmodified detector controls.

The two Python pilot banks each return at most one winning peak per receiver window. The replay timestamps it at the mean of the samples used by the complete pilot frames, then passes the peak to the fixed tracker and position solver. The same tracker processes the bounded native receiver's candidates.

```sh
EVIDENCE=/tmp/receiver-roof-evidence
REPLAY=tools.pipeline_eval.qualification.roof_replays
.venv/bin/python -m "$REPLAY" --panel roof16 --method frontends --jobs 4 --out "$EVIDENCE/roof16-frontend-positions.jsonl.gz"
.venv/bin/python -m "$REPLAY" --panel roof16 --method orbit_interp --method shape_score --method track_reduce --method track_link --method projected_fit --jobs 4 --out "$EVIDENCE/roof16-four-region.jsonl.gz"
.venv/bin/python -m "$REPLAY" --panel ds26-common127 --method frontends --no-check-peak-controls --jobs 4 --out "$EVIDENCE/ds26-common127-frontend-positions.jsonl.gz"
.venv/bin/python -m "$REPLAY" --panel ds26-common127 --method orbit_interp --method projected_fit --jobs 4 --out "$EVIDENCE/ds26-common127-four-region.jsonl.gz"
.venv/bin/python -m "$REPLAY" --panel ds26-common127 --method shape_score --method track_reduce --method track_link --both-offers --jobs 4 --out "$EVIDENCE/ds26-common127-regional-positions.jsonl.gz"
.venv/bin/python -m tools.pipeline_eval figures --evidence "$EVIDENCE" --additional --out /tmp/fresh-roof-figures
```

## Choose recordings

| Panel | Attempts | Contents |
|---|---:|---|
| `smoke` | 2 | DS26-0036 and DS29-0082, each with v5’s original 25 km tile |
| `roof16` | 16 | The eight original DS26 prototype recordings and eight DS29 blind-study recordings, using that same tile |
| `ds26-common127` | 127 | Every DS26 recording that completed all four v5 configurations on both original repeats |
| `ds26-all159` | 159 | The full original roster, including its missing input and failed v5 runs |
| `ds26-excluded32` | 32 | The full DS26 roster minus the 127 common recordings, in original order. Includes the recording with no native detector input |
| `transfer16` | 16 | Two acquisitions per input family, each queried with and without its true region. The checkout includes their verified tracks and orbit catalogues |
| `transfer124` | 124 | All 62 original blind-study acquisition pairs, with their original portable tracks, time-bounded orbit catalogues, and four region offers |

`baseline --panel ds26-common127` reproduces the published v5 distributions. The frozen references include no repair, selective gap, one omitted track and two omitted tracks. DS26 and DS29 were collected at one installation. StarLoc contributes 11 physical captures in eight nearby site groups. Altrincham contributes three empty-track windows. The remaining 40 transfer acquisitions are simulated. The blind-study inputs are now public retrospective test cases. Repeated runs on them do not create a new blind holdout.

Use `replay` for fresh original predictions on the corpus host. The first command reruns the production workers and saves their original scientific archives under `current/evidence`. The second reruns the original regional receiver on the portable inputs.

```sh
.venv/bin/python -m tools.pipeline_eval replay --role all --panel smoke --jobs 2 --pin --out "$OUT"
.venv/bin/python -m tools.pipeline_eval replay --role grid --panel transfer16 --out "$OUT"
```

Pass `--case ID` to limit a command to an explicit subset. The runner puts subset outputs in a separate directory. Each recording is counted once per condition and calibration arm. Error percentiles use returned coordinates. The counts within 1, 2, 5 and 10 km include every attempt in their denominator. Failed workers, missing inputs, withheld positions, and intermediate stage results are counted separately.

## Evaluate another receiver

Export the public input descriptions, run your receiver on each, and write one JSON object per line. The exporter emits the offered regions and input locations. It keeps the correct region, the receiver coordinates, and the reference outputs in the scorer.

```sh
.venv/bin/python -m tools.pipeline_eval export --panel roof16 --out "$OUT"
.venv/bin/python -m tools.pipeline_eval score --panel roof16 --name my_receiver \
  --predictions my-predictions.jsonl --require-v5 --out "$OUT"
```

Each input row has a stable `id`. An external output line has the following shape. The example shows a withheld position in both arms.

```json
{"id":"DS26-0036","result":{"boundary":"native GLRT observations to position","status":"withheld","reason":"insufficient track agreement","metrics":{},"arms":{"c0":{"latlon":null},"fitted_c":{"latlon":null}}}}
```

For a fix, use `status: "ok"` and set each available `latlon` to `[latitude_deg, longitude_deg]`. A stage benchmark omits `arms`. A diagnostic best guess belongs in `forced_latlon`. The scorer admits plain or gzip-compressed JSONL, rejects unknown and duplicate IDs, and counts an omitted recording as missing. Use the complete roster to qualify a panel.

`--require-v5` requires the v5 fix count and count within 5 km for every present dataset and arm. The candidate’s median, P95 and worst error must each equal or improve on v5. A 1 m numerical allowance applies only if all publication decisions match and every returned coordinate lies within 1 m of its paired original. A comparison without a v5 reference also fails this gate. The score includes individual lost fixes and signed paired error differences. Use the transfer results to inspect missed publications and false coordinates when all offered regions are wrong. A single-site roof pass qualifies only that measured panel.

The default output root is `~/.cache/leo/pipeline-eval`. Read `<out>/<panel>/<name>/current/summary.json`, `errors.csv`, and `predictions.jsonl` for the latest completed run. Each rerun keeps a separate generation. Interrupted workers cannot publish partial files as the latest complete result. Full experiment definitions and plugin conventions are in the [protocol](PROTOCOL.md).

## Corpus and build requirements

Raw-IQ, native-detector and prepared-track experiments use different inputs. The corpus resolver verifies available files against the frozen digests. `transfer16` includes a 2.8 MiB compressed bundle of anonymous tracks and orbit catalogues. The larger `transfer124` panel uses the original public tracks in addition to those bundled inputs. The corpus host supplies the archived data under `/srv/bulk`, read-only IQ access for the archive service account, and the historical v5 numerical runtime. Set `PIPELINE_EVAL_BULK_ROOT` to relocate data paths and `PIPELINE_EVAL_BLIND_ROOT` to relocate the directory containing the original `public_field`, `public_field2`, `public_recorded`, and `public_synthetic` trees. Pass `--cache` for a writable local observations directory. Missing inputs produce explicit unavailable outcomes.

Run `python -m tools.pipeline_eval run --variant glrt_batch --panel smoke` on the corpus host for a two-recording, raw-IQ detector smoke test. Rebuild the portable transfer inputs from a verified public archive with `python -m tools.pipeline_eval.frozen.pack_transfer_sample --public-root /path/to/archive --out /tmp/transfer16.zip`.

The original v5 qualification additionally requires its frozen scientific source, native backend, and original archive bindings. The raw `iq_position` path needs the host native short-window GLRT shared library. Set `LEO_PIPELINE_EVAL_GLRT_LIBRARY` to the built `libleo-adaptive-detector.so`. The prepared-track variants use the packaged, pinned numerical reference. [Native detector build](../../native/adaptive/detector/README.md) · [Frozen inputs and source digests](frozen/provenance.json)

## Replay a whole recording

The `full` command accepts a frozen DS26 or DS29 benchmark recording with a supported capture-era release. It rebuilds the inventory from the sealed raw segments, verifies the installed release against the original run ID and runs native fractional GLRT on every eligible window. One numerical worker fits both v5 calibration arms. The scorer compares each resulting position with the survey coordinate and the original v5 outputs. Two raw workers read roughly 10.8 GB of decoded IQ per recording. The preserved receipts and stage times appear under the result’s `current/recording` directory.

```sh
.venv/bin/python -m tools.pipeline_eval full --case DS26-0036 --out "$OUT"
.venv/bin/python -m tools.pipeline_eval full --case DS29-0174 --out "$OUT"
.venv/bin/python -m tools.pipeline_eval full --case DS29-0082 --detector single-rx0 --out "$OUT"
```

The capture-era producer environments are required to read their sealed acquisition contracts. The result reports elapsed seconds and the ratio of elapsed time to the recording's first-to-last window delivery span. This integration tests a different native detector from the capture-era GLRT used to make the frozen v5 inputs. The stage benchmark `glrt_batch` and `glrt_cascade` experiments use the bounded Python pilot bank as their own matched control. Each command identifies its detector in its evidence.

The [measured comparison of all ten directions](../../reports/2026_11_18_pipeline_eval/README.md) includes per-recording errors, the complete-recording replays and the four-region transfer results.

For a raw-IQ positive control without a radio archive, run `python -m pytest -q tests/pipeline_eval/test_iq_position.py`. On a Linux development machine with GCC and the single-precision FFTW development library, it builds the native detector, writes a planted recording, and tests its position, the missing-tile decision and a noise control.

```sh
.venv/bin/python -m pytest -q tests/pipeline_eval
```

## Run the accelerated original receiver on saved I/Q

The original receiver command authenticates saved 10 MS/s segments, runs the installed capture policy with the prepared FFT kernel, and passes freshly measured native factors to the compact `c = 0` and fitted-`c` solver. It accepts a known `--case` or a recording locator supplied with `--input` and its trusted `--input-sha256`. A standalone input needs a truth-free numerical request template, causal TLEs, and TrackConfig. It can omit all previous detector output fields. Use a new local output directory and an explicit list of available cores. [Command, input format, and measured checks](../../reports/2026_11_19_receiver_screening/original-support/receiver-command/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --accelerated --case DS26-0237 --out /var/tmp/original-ds26-0237 \
  --cpus 0 1 2 3 4 5 6 7 --raw-limit 600 --position-limit 180
```

For a bounded launch check, pass `--smoke` and one CPU. The command authenticates and processes the first complete chunk, records partial coverage and leaves position unmeasured. Full runs write `summary.json`, the measured `native.json`, and `position/position.json` when the numerical worker returns.

`--accelerated` keeps the original pilot schedule and pairs a stored 256-point coarse FFT with row-wise peak selection and the four-frame batched fine-frequency search. The source lock and summary record the selected coarse plan. The prepared 512-point FFT remains the default when the switch is omitted. Explicit peak-selector and fine-search arguments take precedence over the preset. [Measured receiver command](../../reports/2026_11_19_receiver_screening/original-schedule/accelerated-command/README.md)

## Run the standalone C detector through position

The portable replay runs the two antenna searches and their gate-driven retries from the saved samples, then passes its own GLRT measurements to both compact calibration fits. It accepts the same authenticated case or recording locator as the original receiver. On the recording archive host, choose available CPU numbers and a new local output directory.

```sh
.venv/bin/python -m tools.pipeline_eval.portable_receiver \
  --case DS29-0082 --cpus 3 4 5 6 7 --raw-limit 600 --position-limit 180 \
  --out /var/tmp/portable-ds29-0082
```

Use `--input LOCATOR.json --input-sha256 DIGEST` for another compatible recording or `--smoke` with one CPU to process the first signed chunk. The full run writes the source lock, candidate and timing evidence, and both position results. The standard benchmark regenerates the plots and CSVs from the completed evaluations. [DS26 measurements](../../reports/2026_11_19_receiver_screening/native-receiver/portable-field/README.md) · [DS29 measurements](../../reports/2026_11_19_receiver_screening/native-receiver/portable-command/README.md)

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study reports/2026_11_19_receiver_screening/native-receiver --pack \
  --out /var/tmp/native-receiver-charts
```
