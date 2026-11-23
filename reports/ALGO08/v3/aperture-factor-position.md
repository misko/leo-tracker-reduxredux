# Fixed-center aperture factors through dense DS30-0008 position

Replacing measured prefix results on the first 48 authenticated stereo visits reduced horizontal error from **919.0 to 814.5 m** with `c = 0` and **857.4 to 721.3 m** with fitted `c`. The complete installed-graph solver used **28.444 CPU s** versus **24.739 CPU s** for the matched prefix. Both positions passed publication. The experiment covers 80 of the recording's 13,530 possible lane measurements and establishes the solver response to this partial replacement. Full-recording centering remains unmeasured. [Frozen protocol](aperture-factor-position-protocol.md) · [Signed science and timing receipt](measurements/aperture-factor-position.json.gz)

## Receiver and chronological selection

The same fixed central `[40000, 160000)` sample aperture applied to every enrolled primary. The signed join checked original probe metadata, exact complete prefix receiver tuples or absence, and the original per-window I/Q digests in the authenticated first index. It covered 80 short-primary lanes and separately verified 16 measured full anchors. Of the 80 substituted primary slots, 35 had changed complete tuples, two gained a positive factor, and 43 stayed empty. The unchanged native outputs on all 1,696 anchor lanes yielded the same 956 anchor detections. Unfiltered receiver observations rose from **7,336 to 7,338**. The derived packet retains the original recording authority and carries its own detector recipe, analysis and native digests. [Factor substitutions and full packet identities](measurements/aperture-factor-position.json.gz)

The released causal continuation was replayed from the beginning on both full streams, including every untouched later lane. It selected **5,940 factors** in each arm with four membership differences. Centered admitted receiver 0 at visits 44 and 56 and removed it at visits 77 and 94. The latter three changes occurred after the signed replacement interval. The control and candidate agreed on all anchor continuation decisions. The position comparison used the unfiltered native full-coverage handoff, as in the saved 26.105 s solver reference. [Released continuation](../../../tools/pipeline_eval/variants/carrier_continuation.py) · [Original unfiltered solver](regional-dense-pair.md)

## Position, residuals and owners

| Calibration arm | Prefix endpoint | Partial center endpoint | Shift m | Horizontal error m, prefix → center | RF RMS Hz, prefix → center |
|---|---|---|---:|---:|---:|
| `c = 0` | 37.841516439, −122.481468340 | 37.842188616, −122.482530002 | 119.5 | 919.0 → 814.5 | 140.9614 → 140.4726 |
| Fitted `c` | 37.841825268, −122.482363939 | 37.842650281, −122.484462650 | 205.9 | 857.4 → 721.3 | 140.9498 → 140.4543 |

The track graph went from **208 to 211 tracks** and **6,461 to 6,492 assigned points**. The selected owner count fell from **4,367 to 4,288** in each calibration arm. Of 4,262 shared physical lanes, 11 changed CFO. Among the 4,251 with identical timing and CFO, 21 changed role and zero changed satellite. The fit lost 105 owner lanes and took on 26. Each 179-point grid reproduced its two endpoints' objectives exactly. The position path differed between recipes, and all eight PNGs differed in both file and decoded-pixel digests. The fresh prefix reproduced the archived terminal, owners and roles, numerical grid, position path and eight PNGs. Its stored grid elapsed field was the sole archived grid payload difference. [Complete grids, owners, image digests and positions](measurements/aperture-factor-position.json.gz)

## Clocks and feasible receiver cost

| Measured scope | Prefix CPU / elapsed s | Partial center CPU / elapsed s |
|---|---:|---:|
| Saved worker through exit | 29.242 / 30.341 | 32.990 / 33.029 |
| Saved publication | 27.766 / 28.829 | 31.467 / 31.492 |
| Numerical solve through full grid | 24.739 / 24.755 | 28.444 / 28.466 |
| Cold discovery and finalist fit | 5.809 / 5.813 | 7.255 / 7.260 |
| Signed completion | 0.613 / 0.614 | 3.290 / 3.293 |

The cold finalist race completed one fit with prefix and three with partial center. Both warm signed arms failed their stationarity check with partial center, so that case paid 2.549 CPU s for the original paired refit. These branch changes explain most of the observed increase. The frozen native receiver comparison used one call per antenna and no input copy. Its complete callback cost differed by **+0.78% and +0.28% CPU** in the two measured dense orders. The 28.444 s partial-center solve exceeds the modeled 14.067 s first-four allowance at the favorable measured acquisition-prefix rate. This saved experiment excludes native acquisition and does not estimate a whole-recording speedup. [Matched branch clocks](measurements/aperture-factor-position.json.gz) · [Native callback and I/Q checks](centered-primary.md) · [Same-input solver budget](regional-dense-pair.md)

## Reproduce

The first launch stopped before inference because an eager import precluded the frozen worker's lazy startup. The recorded run uses the corrected launcher at `dd03451b6`, whose source SHA-256 is `fbd608cebfca4ee72f228fb369cdcc30ffd8afdb007663f57a5b49f95428a89b`. Both complete publications are retained at `/dev/shm/leo-aperture-factor-position-02`. Run as an account that can read the original signed acquisition index, archived detector and causal catalogue. Use a fresh output path. [Replay and post-seal verifier](aperture_factor_position.py) · [Component tests](../../../tests/pipeline_eval/test_aperture_factor_position.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /dev/shm/leo-aperture-factor-position.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
  "$release/venv/bin/python" -BPs "$here/aperture_factor_position.py" launch \
  /var/tmp/leo-full-short-dense-DS30-0008 "$here/measurements/centered-primary.json.gz" \
  "$out/pair" /var/tmp/leo-regional-track.O238AD0C/scores.so
gauss env PYTHONPATH="$here:$PWD/src:$release/src:$PWD" \
  "$release/venv/bin/python" -BPs "$here/aperture_factor_position.py" score "$out/pair" "$out/scored.json"
```
