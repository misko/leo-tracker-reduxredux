# Dense DS30-0008 crossover on the actual full-short detector

On the authenticated full-short DS30-0008 detections, the installed graph reduced complete solve CPU from **30.245 to 25.566 seconds** and horizontal error from **1.289 / 1.138 km to 0.919 / 0.857 km**, in fixed-zero and fitted calibration order. The RF residual increased from **138.764 / 138.654 Hz to 140.961 / 140.950 Hz**. The saved replay kept the same detector document, 25 km offer, causal archive, fused geography, finalist race, signed finish and numerical evidence. [Frozen protocol](dense-full-short-crossover-protocol.md) · [Four-cell receipt](measurements/dense-full-short-crossover-summary.json)

| Detector × graph | Solve CPU s | Solve elapsed s | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` | Owners per arm |
|---|---:|---:|---:|---:|---:|
| Installed × installed, archived saved | 30.064 | 30.147 | 1.088 / 1.079 | 128.822 / 128.753 | 4,440 |
| Installed × quadratic, archived saved | 37.428 | 37.431 | 2.603 / 2.512 | 127.140 / 127.024 | 4,328 |
| Full-short × installed, new saved replay | **25.566** | **25.568** | **0.919 / 0.857** | 140.961 / 140.950 | 4,367 |
| Full-short × quadratic, actual raw solve subclock | 30.245 | 30.249 | 1.289 / 1.138 | 138.764 / 138.654 | 4,146 |

All four cells use the same fused geographic DSO. The older numerical replays are from the original installed-detector archive. The short-detector cells share the exact native digest `sha256:ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85`. Their signed input binds to the same session, inventory, raw authority, chronology and 13,530 stereo-lane opportunities as the installed detector. The independent comparison checked the sealed 6,772 scheduled and 6,765 admitted visits, the full anchor and independent 12 ms schedule, original catalogue snapshots, and the quadratic candidate's raw terminal, owner digests, path, grid and all eight original figure hashes. [Installed-graph fused replay](dense-geographic-kernel.md) · [Quadratic-graph fused replay](dense-quadratic-fused.md) · [Complete crossover record](measurements/dense-full-short-crossover.json.gz)

## Position and association

Switching from installed to quadratic graph increased horizontal error **1.515 / 1.432 km** on installed detections and **0.370 / 0.281 km** on actual short detections. The short detector with installed graph improved **0.169 / 0.222 km** over installed detector with installed graph. The actual raw combination with quadratic graph worsened **0.201 / 0.059 km** against that same installed-detector comparator. Those last deltas clear the historical 250 m triage screen and remain worse in both arms. The graph's effect on error differed by **−1.145 / −1.152 km** between detector packets. This single capture measures a detector–graph interaction on the offered region.

The actual short packet has 7,336 selected observations. The installed graph prepared 208 tracks and 6,461 assigned points. The quadratic graph prepared 324 tracks and 6,700 assigned points. On short detections the graph switch shared 3,907 owners per arm, changed satellite for six and role for 535, removed 460 and added 239. A detector switch under the installed graph shared 3,781 receiver/RF/edge/sample-counter measurements per arm. Of those, 482 kept the same CFO and fractional epoch, with one satellite change and 18 role changes among that exact-factor subset. Both arms showed the same membership counts. [Owner comparisons](measurements/dense-full-short-crossover-summary.json)

Both calibration arms on every cell completed a 179-node grid. Each grid minimized at its corresponding endpoint and reproduced its endpoint objective with zero difference. The early geographic proof issued 25 probes and stopped on `inside_score` for every cell, with zero withholding or installed-solver fallback. The installed-detector quadratic run completed all three finalists after an ambiguous prefix and paid 2.749 CPU seconds for the original cold signed refit. The other three cells completed one finalist and passed both warm signed arms.

## Timing boundaries

On actual short detections, early geography used **3.864 CPU seconds** with the installed graph and **4.692** with the quadratic graph. Cold work used **6.320 / 7.142** and standard numerical evidence **6.133 / 7.816** in installed-graph and quadratic-graph order. The two short rows compare matched solve subclocks from independently executed raw and saved processes. The raw subclock includes inference binding. The new saved clock starts immediately before the installed solve after attaching the same options. Both clocks include track preparation through complete numerical grids.

The raw quadratic candidate's whole process used **67.352 CPU / 95.429 elapsed seconds**, including raw acquisition, verification and rendering. Its analysis publication used **65.888 / 93.964** and its acquisition used **32.403 / 60.449**. The new saved numerical replay leaves those scopes outside its solve clock and leaves the original publication intact. Performance with the installed graph through a new complete raw run remains unmeasured. [Raw and saved timing scopes](measurements/dense-full-short-crossover-summary.json)

## Reproduce

Use the existing sealed raw output rooted at `/var/tmp/leo-full-short-dense-DS30-0008`, its original fused library and a new output directory. The runner reads only the archived detection and publication documents. Score once the single saved output seals. Thirty-one component and adjacent tests passed. [Replay](dense_full_short_crossover.py) · [Scorer](dense_full_short_crossover_score.py) · [Tests](../../../tests/pipeline_eval/test_dense_full_short_crossover.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
raw=/var/tmp/leo-full-short-dense-DS30-0008
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /var/tmp/dense-full-short-crossover.XXXXXXXX)
geo=$(jq -r '.command[.command|index("--geographic-library")+1]' "$raw/binding.json")
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 120s \
    env OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
  "$release/venv/bin/python" -BPs "$here/dense_full_short_crossover.py" \
  "$raw/publication" "$raw/process.json" "$geo" "$out/replay.json"
gauss env PYTHONPATH="$here:$PWD/src:$PWD" \
  "$release/venv/bin/python" -BPs "$here/dense_full_short_crossover_score.py" \
  "$raw/publication" "$out/replay.json" "$out"
```
