# Shared normalized frame layout for covariance and both mode projections

The frame-plane receiver saved **5.26%** paired native CPU on the 18-window DS26 weak-carrier archive and **5.13%** on the measured Austin excerpt. The **frame planes plus tiled FIR** saved **7.64%** on DS26 and **6.46–7.81%** on Austin's measured inputs. The composed build preserved every tested factor and continuation decision. It also reproduced all exported factors on the three old wrapped-CFO regression lanes. [Standalone clocks](measurements/receiver-frame-planes.json) · [Composed clocks](measurements/receiver-frame-planes-composed.json.gz) · [Wrapped regression](measurements/receiver-frame-planes-regression.json)

## Full-support mode construction

The earlier packed receiver spent 99.54 ms in mode construction over 360 scouts, 14.7% of complete native CPU on that weak-carrier profile. Its pairwise kernel loaded interleaved signal from the same normalized frames and deinterleaved those values for each covariance pair. The prototype writes each float-normalized frame once into real and imaginary planes with matching four-sample stripes across two frames. One load supplies both partner real vectors and another supplies both imaginary vectors. The existing frame allocation holds this layout. Both projections use the same samples again and keep each four-sample output in registers while visiting all 14 frame weights in order. [Original paired kernel](receiver-mode-pair.md) · [Earlier stage clocks](measurements/receiver-packed-cancellation.json) · [Shared-layout implementation](../../../tools/pipeline_eval/variants/experimental/receiver_frame_planes.inc)

The means, squared norm and centering arithmetic are unchanged. Each covariance entry keeps its four Float32 accumulation chains and their final fold order. The Jacobi updates, strict mode ordering, and per-sample projection reduction order remain the same. Unsupported ISA and widths with partial stripes take the interleaved calculation. Both passes retain all measured frame support, run the same timing and carrier scouts and confirmation gates, and keep signed cancellation and full-rate verification. A reduced covariance gate was already rejected on an independent weak factor. Reusing covariance after signed cancellation was also ruled out because every normalized row intersected changed samples. This trial computes the full matrix independently on both passes. [Rejected gate](receiver-covariance-confirmation.md) · [Residual support](receiver-cancel-support.md)

| Measured boundary | Wrapped d97b | Frame planes | Median paired saving |
|---|---:|---:|---:|
| Full mode construction on one generated Float32 lane | 271.4 µs | 165.3 µs | 39.1% |
| DS26 weak-carrier stereo, 36 native calls | 139.38 ms | 131.51 ms | 5.26% |
| Austin measured, 4 one-antenna calls | 17.09 ms | 16.19 ms | 5.13% |
| Austin phase nulls, 4 one-antenna calls | 7.11 ms | 6.60 ms | 7.23% |

The isolated fixture exercises normalization through both complete ordered mode arrays. Its first comparison exposed a compiler-dependent diagonal reduction in the unprofiled fixture. The archived PGO receiver calls the diagonal dot product out of line, with four ordered chains. Applying that call boundary to the fixture reproduced both mode arrays byte for byte. Four component tests passed across both native widths, signed zeros, tied eigenvalues, and unsupported stripe geometry. The full receiver trial uses the original wrapped binary as the reference. The source change rebuilds only the timing translation unit, using the previous site-free compiler feedback signals. All 66 factor tuples and continuation results matched on the weak and Austin samples. [Fixture and standalone build](receiver_frame_planes_trial.py) · [Tests](../../../tests/pipeline_eval/test_experimental_receiver_frame_planes.py)

## Composed receiver

The builder pins and relinks the standalone tiled FIR binary, then substitutes only the already tested frame-plane timing object. It verifies source and object SHA-256 digests and the complete dynamic symbol list. The wrapped refinement, exact signed cancellation, and verifier objects remain the archived ones. The resulting binary is `/tmp/leo-algo08v2-2x-bench/d97b-planes-and-fir/receiver.so`, with SHA-256 `14b52e7e85b6fcf94c956acb3da579d711959c3313d1bc6b9522128c5f161e7c`. [Link command and pins](measurements/receiver-frame-planes-composed.json.gz) · [FIR tile](receiver-fir-tile.md)

| Archived sample | Wrapped d97b | Composed | Median paired saving |
|---|---:|---:|---:|
| DS26 weak-carrier stereo, 36 lanes | 136.30 ms | 124.98 ms | 7.64% |
| Austin measured, 4 zero-center calls | 15.87 ms | 14.72 ms | 7.81% |
| Austin measured, 4 shifted-center calls | 19.95 ms | 18.59 ms | 6.46% |
| Austin null, 4 zero-center calls | 6.51 ms | 5.85 ms | 10.07% |
| Austin null, 4 shifted-center calls | 7.57 ms | 6.89 ms | 8.55% |

Twelve repeats alternate native call order across all 52 lane configurations. All 74 factor records, including 30 residuals, matched byte for byte. Every continuation preference, vote count and selection matched. The archive has no continued selections at these spacings. Both Austin phase-null configurations at each pilot edge stayed empty. The shifted-center test uses −50 kHz on the lower edge and +50 kHz on the upper edge. The timings exclude archive reads and continuation. The weak-slice paired difference of **296 µs per lane** would correspond to about 2.75 CPU s across the 9,288 admitted calls in the previous DS30-0374 physical recording if that rate carried through every lane. These trials measured only the receiver, and the active-scout mix on a full recording may differ. [Paired native receipt](measurements/receiver-frame-planes-composed.json.gz)

The three DS30-0008 regression visits use the original authenticated lane, I/Q, and scan bindings. The composed binary matched the archived full restoration and a fresh readout of that same restored binary for all five factors. The recovered primary carriers are 423233.6713368766, −85797.21886355223 and −96538.83871655293 Hz. Fractional epochs and both scores also matched the restoration. [Regression receipt](measurements/receiver-frame-planes-regression.json) · [Original CFO lineage](receiver-cfo-lineage.md)

## Reproduction

Run each command through the shared Gauss lock with CPU 2, low CPU and I/O priority, and one numerical thread. The standalone frame trial accepts the archived two-scan build tree, release assets, saved weak ZIP and standard Austin inputs. The composed builder uses the two verified standalone object directories, then the regression subcommand uses the paired DS30-0008 binding as the `leo` account. It reads only the original three regression lanes. [Standalone driver](receiver_frame_planes_trial.py) · [Composition and regression driver](receiver_frame_planes_composed.py)

~~~bash
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist="$tree/reports/2026_11_19_receiver_screening"
weak="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
austin=/home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip
audit="$hist/physical/raw-source-audit.json"
wide="$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
saved=/tmp/ds30-v2-stage-covariance-375895/DS30-0008
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_frame_planes_trial \
  "$p/d97b-frame-planes-rebuild" "$p" "$r/assets" "$weak" "$austin" "$audit" "$wide"
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_frame_planes_composed \
  compose "$p/d97b-planes-and-fir-rebuild" "$p" "$r/assets" "$weak" "$austin" "$audit" "$wide"
lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" "$r/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.receiver_frame_planes_composed regression \
  "$p/d97b-planes-and-fir-rebuild" "$p" "$r/assets" "$saved/pair.json" \
  "$saved/candidate/fast-scan-automatic-work/algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk
~~~
