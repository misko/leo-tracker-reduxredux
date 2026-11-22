# Signed orbital prior with the fast receiver and the regional guard

Freeze the combined candidate before evaluating another roof recording. Use the compiler-trained Q15 dual-entry receiver, the conditional residual schedule, collapsed discovery with paired repair, the released signed orbital prior, and the boundary guard with same-solve catalogue reuse. The solver applies the signed update under the original causal qualification and paired acceptance rules at every location. The build specification digest is `sha256:f7dcc16dc41d5d923a9d7e75ec094ca9a2cb42c8aba9ce1316d6c2af50b971e4`.

First check the complete pipeline on the public northern 100 m inside offer against deployed ALGO08v2, with the candidate first. Then try the solver alone on the archived DS30-0155 conditional detections. DS30-0155 had the largest loss in position accuracy in the earlier four-recording development stage. Both solvers receive that entire same ordered measurement file, assigned region and capture-time archive. Compare the two horizontal errors against both the matched conditional control and deployment; report frequency-fit changes separately. This check uses an earlier detector file and does not measure the combined receiver's output or end-to-end time on DS30-0155. Keep the complete 16-recording stage and fresh geographic confirmation sealed.

## Complete northern boundary result

Elapsed time fell **32.84 → 16.54 seconds (1.986×)** and CPU time fell **31.99 → 16.12 seconds (1.984×)**. Both runs incurred zero filesystem input blocks. The candidate missed the 0.500 elapsed ratio by 0.118 seconds on this pair. Its fixed-zero error was 106 m and its fitted error was 141 m, exactly matching deployment. All 456 selected radio observations, both owner maps, the numerical grid and path, and all eight decoded web figures matched. A single simulated recording cannot establish the benchmark distribution. [Pair](measurements/north-edge-signed.json) · [Scientific audit](measurements/signed-repair-triage.json)

![Elapsed time, single-core CPU and position error. North uses conditional second scans and South uses full second scans.](signed-publication.png)

The previous collapsed solver stopped after fitting the unsigned orbital phase prior. On identical observations its fitted position was 212 m from truth. The restored correction uses differences between satellite orbital elements observed before capture. It reproduced deployment's 141 m error. The guard also reused the full causal satellite catalogue already prepared during this solve. Each offer still evaluates all 96 regional probes when the optimizer reaches a bound. [Signed update and causal provenance](solver-stock-finish.md) · [Matched guard scores and cost](regional-bound-guard.md)

On the same detector file the signed solver withheld the distant omitted region. Moving the valid boundary square 200 m to put the receiver 100 m outside still yielded a false fix, 123 m and 118 m from truth in the two arms. These are saved-detection decision checks. They do not contribute to the raw-to-web timing.

## Crossing detector inputs and solvers on DS30-0155

| Saved measurements | Position solver | Error with `c = 0` | Error with fitted `c` | Frequency RMS with `c = 0` / fitted |
|---|---|---:|---:|---:|
| Deployed, full second scans | Deployed | 0.972 km | 1.157 km | 155.42 / 155.38 Hz |
| Same full measurements | Collapsed with signed update | 0.972 km | 1.157 km | 155.42 / 155.38 Hz |
| Earlier conditional second scans | Shared-tables control | 1.291 km | 1.426 km | 156.08 / 156.06 Hz |
| Same conditional measurements | Collapsed with signed update | 1.323 km | 1.464 km | 156.37 / 156.32 Hz |

On the full measurements the signed solver reproduced both deployed endpoints, both 3,498-observation owner maps, the path and the 179-point grid. On conditional measurements, changing the solver added another 0.037 km of fitted error. Switching the input of the signed solver from conditional to full recovered 0.307 km. The combination of input and solver matters. This recording had already been used to investigate conditional scans and cannot serve as blind confirmation. [Ordered input digests, scored runs and numerical evidence](measurements/signed-repair-triage.json)

## Full two-scan receiver on the original DS30-0155 I/Q

Run both scans on every admitted lane, retain the floating-point FIR, and compile the full receiver using the same site-free training signals. This removes the conditional second-scan schedule. Freeze that receiver with the signed solver and same-solve catalogue reuse. A single raw-to-web run took **75.08 CPU seconds and 118.23 elapsed seconds**. It returned both fixes and all eight PNGs. The fitted position error was **1.157 km** and fixed-zero error was **0.972 km**. These match deployment to the precision shown. [Raw run and comparison](measurements/full-float-signed-0155.json)

All 4,627 returned observations retained their winning rank. Two had small numerical changes; the larger CFO difference was 0.000096 Hz. Both satellite owner maps matched. The positions moved by less than 0.00002 m. Seven decoded PNGs matched exactly. The position image, grid and path differed. [Per-observation differences and image checks](measurements/full-float-signed-0155.json)

The previously archived deployed run on the same raw input took **144.70 CPU seconds and 148.20 elapsed seconds**. It reported 40 filesystem input blocks, versus 16,249,328 in the new run. The historical CPU ratio is 1.93×. The gap to half the archived CPU is 2.73 s. This was a candidate-only timing and cannot establish paired elapsed speedup. The frozen full-scan specification is `sha256:99b46f7ffe4d9e2acb173364d54240c6cf8ca2deceb1d7715d389c03066659cf`. Build its detector with `receiver_compiler_trial.py build "$FULL_BUILD" "$ASSETS" --floating`, then freeze the same signed solver with `--schedule all`. [Compiler and build procedure](receiver-compiler.md)

## The same full-scan build on the southern simulation

With the receiver 100 m inside its supplied square, deployed ALGO08v2 took **35.44 s** and the full-scan signed candidate took **16.04 s** from raw I/Q through all eight PNGs, a **2.21× paired elapsed speedup**. Single-core CPU fell from 31.08 to 15.44 s (2.01×). Both runs reported zero filesystem input blocks and returned 0.817 km fixed-zero error and 1.101 km fitted error. All selected observations, owner maps, grid, path and eight decoded images matched. The northern row in the figure used conditional second scans. Pooling those two rows would mix candidate builds. [Southern matched pair](measurements/south-edge-full-signed.json)

Reusing the southern full-scan detections, the candidate withheld both arms on the distant omission but returned a false fix when the receiver was 100 m outside. That fitted error was 1.102 km. The two hemispheres expose the same remaining decision failure. This is a public development simulation, and physical position accuracy away from the Gauss site remains unmeasured. [Saved wrong-region receipts](measurements/signed-repair-triage.json) · [Across-face bias at both sites](mirrored-regions.md)
