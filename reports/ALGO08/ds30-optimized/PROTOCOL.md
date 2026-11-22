# Staged DS30 replay on Gauss

Start with four recordings on one worker. Use the first 4 (`smoke`), 16 (`triage`), 64 (`expanded`) or 455 (`full`) members of the frozen DS30 prediction order. Each stage stops on completion. The panels are nested, so the same results directory can reuse completed recordings from a smaller panel. Every chosen member counts, including partial captures and solver failures. Alternate the first pipeline by the recording's index in the frozen order. The detector, solver, region and cohort were fixed before the first replay.

Use the four-recording check to catch differences in detector measurements, fix decisions and coordinates. Use 16 pairs to see whether the timing effect survives both run orders. Inspect individual differences before expanding to 64. Reserve the full set for a release decision or a specific question the smaller panels leave open.

The published 16-recording triage panel reuses results saved before the larger replay was stopped to release Gauss capacity. That replay ran up to 20 independent recording pairs concurrently. The elapsed timings include that contention. Scoring these 16 pairs required no new raw-I/Q reads. The panel is a descriptive check at one station and its tail percentiles can move substantially with a few recordings.

Each pipeline starts at the committed short-window segment manifests and reads the sealed signed stereo I/Q through the installed ALGO08 acquisition function. Each runs its own file read, payload verification, two-scan detection, causal candidate selection, satellite preparation, association, fitted and fixed-zero calibration, position and diagnostic-grid computation. Both use the November 21 Gauss regional release `081ab0265`, the same pilot assets, 25 km station search square, historical sky-screen center and the recording's frozen TLE archive. The scorer reads the station reference after the prediction streams are locked. The deployed receiver digest is `98d094c9541d22a94396df9ce00778c20030fcf88ac52257bd975b304b916cb5`. The experimental receiver digest is `f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809`.

The loader binds each recording and segment to its frozen digest. Archive paths may move between the short-term storage and permanent fast-scan archive. Before timing a pair, the harness verifies the frozen native packet, copies its input-manifest identifier and discards the packet. Each timed arm opens the raw segments, regenerates every detector measurement and passes its own new packet to the solver. Both reads must reproduce the committed raw recording authority, number of windows and number of eligible antenna visits. The executable changes only the detector library argument and the corresponding digest in the research process. Both pipelines call the installed position solver in its qualified numerical environment and independently calculate both calibration arms. Production services and their caches are outside this experiment.

Bind each pair to the same Gauss CPU and use one numerical thread. The two executions are consecutive for each recording. Multiple recordings may run concurrently. Wall time measures the complete raw-to-position interval, including contention and effects of the OS file cache. Process CPU is a complementary measure. Record acquisition, fit and total time on both clocks. The timer excludes selecting the benchmark member, reading its frozen binding, post-run equivalence checks, PNG encoding and web publication. The fit includes the release's conditional diagnostic grid. Record which arm ran first and report both orders. Short captures can have negligible elapsed times.

Count every recording in fix coverage and cumulative error plots. Report returned-position medians, P90 and P95, counts within 1 km over all assigned recordings, and solver frequency RMS separately. Report exact decision, position, post-history factor and final-owner equivalence, and reconcile the fresh deployed baseline against the published regional DS30 replay. Count the known cavity error on DS30-0340 if the solver raises it. An infrastructure exception leaves a missing receipt and prevents a complete report. Preserve individual recording timings across restarts.

The reporting code was smoke-tested on four already completed pairs covering a successful fix, withholding and the known solver failure. Their decisions and both scoring arms were reconciled with the previously public DS30 results. For any published panel, the scoring command locks both receipts for every selected recording before loading the reference coordinates.

## Reproduction

Use the [frozen cohort](../../2026_11_21_ds30_full/cohort.json), its historical Gauss bindings and the installed release named above. The research [source archive](receiver-source.zip) includes the exact C sources and compiler arguments. The following commands build the shared library with the qualified Gauss toolchain. The printed SHA-256 must match the experimental digest above.

```sh
study=reports/ALGO08/ds30-optimized
work=$(mktemp -d)
unzip -q "$study/receiver-source.zip" -d "$work"
python3 - "$work" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
build = json.loads((root / "build.json").read_bytes())
for name, expected in build["source_digests"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
subprocess.run([build["cc"], *build["args"], "-o", "receiver.so"], cwd=root, check=True)
print(hashlib.sha256((root / "receiver.so").read_bytes()).hexdigest())
PY
```

Under an account with read access to the station recordings, keep one results directory per receiver build and timing configuration. The commands below use one low-priority worker and four recordings. To reproduce the published selection using saved measurements, run only the scoring and verification commands with `panel=triage`. Fresh one-worker measurements use a separate results directory from the high-concurrency study.

```sh
release=/opt/leo-algo08/081ab0265a9d37dbc2d3fb5b62a64d02970b67ed
panel=smoke
export PYTHONPATH="$PWD/$study:$release/src:$release" OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
ionice -c2 -n6 nice -n8 "$release/venv/bin/python" -BPs "$study/run.py" "$work/receiver.so" "$RESULTS" --panel "$panel"
"$release/venv/bin/python" -BPs "$study/score.py" "$RESULTS" "$study" --panel "$panel"
"$release/venv/bin/python" -BPs "$study/verify.py" "$study"
```
