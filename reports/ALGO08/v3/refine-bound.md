# Pruning individual full-rate hypotheses in the two-scan receiver

The even-frame bound saved **2.0% of native receiver CPU on weak lanes and 2.6% on dense lanes** against installed ALGO08v3 after rebuilding with its original profile-guided compiler recipe. The unprofiled build had run slower than installed v3. The strongest audited bound projects about **1.19 seconds** of avoided work on the full dense DS30-0008 recording before the bound and other overhead.

The audit replayed v3 on all 18 previously nominated DS26 weak-carrier stereo visits and the first 48 authenticated DS30-0008 visits. The bound applies after the quarter-rate scout selects four signed frequency and timing hypotheses, on both the raw scan and the actual signed residual. Both arms preserved the ordered factors, including all 50 residual factors, and the single causal continuation selection across 132 independent lane calls. The replays stopped at continuation. [Per-lane evidence and I/Q identities](measurements/refine-bound-audit.json.gz)

## What can be skipped

Each hypothesis searches nine timing offsets, each with eight full-rate pilot block correlations for each of 14 frames. The score at an offset is the smaller of the normalized even- and odd-frame coherent powers. The correction frequency is inferred from both groups, so a group alone needs an enclosure over every possible correction before it can certify that the other seven frames are unnecessary.

Let \(z_{f,b}\) be the frozen Float32 complex correlation of block \(b\) in frame \(f\), and let \(D_g=\max(E_g E_{\mathrm{pilot}},10^{-15})\) be the original denominator for frame parity \(g\). The triangle inequality bounds the contribution of either parity by

\[
 U_g/ D_g = \frac{\sum_{f\in g}(\sum_{b=0}^{7}|z_{f,b}|)^2}{D_g}.
\]

The tighter audit uses the degree-seven squared-norm trigonometric polynomial from the eight blocks. The frozen correction is an `atan2` phase divided by four block spacings, so the rotation per block is within \(\pi/4\) of zero, with padding for frequency rounding. On each of eight equal intervals, the larger endpoint plus \(M h^2/8\) bounds the polynomial, where \(h\) is the interval width and \(M\) bounds the second derivative using the lag coefficients of the polynomial. It can use the smaller of this bound and the triangle bound. The source for both bounds uses the original block products and power reduction order. It checks that the complete single-candidate output equals the frozen bank's output byte for byte and that every observed exact score lies below its enclosure. [Enclosure and AVX2 prototype](../../../tools/pipeline_eval/variants/experimental/receiver_refine_bound.c)

The AVX2 trial uses the less expensive triangle bound. Its numerator allowance is \(2^{-33}\) times the triangle numerator plus a tiny floor, with a final upward `nextafter`. It covers the short Float64 dot-product and sum reductions relative to the uncancelled magnitude, including cancellation and the ordinary rounding of unit phase rotations under the Gauss math library. This argument assumes round-to-nearest arithmetic and small error in the library phase functions. The study checked observed scores and rank ties and did not independently qualify the math library across platforms. Nonfinite enclosures, wrapped offsets and unsupported CPUs retain the bank's full evaluation. The previously tested Cauchy–Schwarz implementation uses a larger rounding allowance and yielded 0.6–1.7% native CPU savings against its earlier receiver baseline. [Earlier parity study](../single-core-2x/receiver-refine-parity.md)

The prototype fully refines and independently confirms the first seed before using its exact score as a cutline. A seed is pruned only when the upper bound at all nine timing offsets falls strictly below the cutline. Any available candidate that could beat the incumbent keeps all offsets, its exact interpolation and its original gate. Fully refined survivors run in their original descending score and request order. The first seed wins exact ties by the frozen rule. If it fails the gate, the bank fully refines and ranks every remaining seed. The provisional result is local to a scan. The original receiver still constructs the signed residual from the confirmed first scan and runs the original independent fractional verifier and causal continuation. [Pilot and continuation replay](../../../tools/pipeline_eval/variants/experimental/receiver_refine_bound.py)

## Work ceiling

| Slice and scan | Scouts | Hypotheses | Oracle omissions | Triangle parity omissions | Restricted parity omissions |
|---|---:|---:|---:|---:|---:|
| Weak raw | 36 | 144 | 108 | 89 | 100 |
| Weak residual | 36 | 144 | 66 | 53 | 65 |
| Dense raw | 96 | 384 | 156 | 119 | 148 |
| Dense residual | 52 | 208 | 84 | 66 | 82 |

The oracle knows the confirmed winner and omits every other full refinement in those scans. It charges all hypotheses on unconfirmed scans. The parity columns count seven of the 14 frames avoided for each certified seed. They model a sequential confirmed incumbent and exclude the cost of checking a bound. The tighter certificate drops 165/576 weak and 230/1,184 dense half-bank block sets. The prototype's fixed first-seed cutline and triangle bound drop 137/576 weak and 183/1,184 dense. One half-bank set covers all nine offsets for a single candidate and one parity. These counts omit oscillator setup, shared sample loads, bound overhead, interpolation and additional gate calls.

| Slice | Installed native CPU / elapsed | Clocked bank CPU / elapsed | Whole native CPU share in the bank | Oracle share of native CPU, linear model | Restricted share of native CPU, linear model |
|---|---:|---:|---:|---:|---:|
| Weak | 142.19 / 142.25 ms | 20.86 / 20.91 ms | 14.7% | 8.9% | 4.2% |
| Dense | 259.26 / 259.37 ms | 43.44 / 43.51 ms | 16.8% | 6.8% | 3.3% |

The CPU projection assigns the traced bank's median clock linearly to the avoided work and assumes the per-lane dense mix transfers to 13,530 lanes. Removing the entire bank gives roughly **6.1 CPU seconds** as the broad stage ceiling. Giving the oracle free ranking and removing every known loser gives **2.5 seconds**. The tighter parity count gives **1.19 CPU seconds** before cost. It corresponds to roughly 2.3% of the full warm acquisition's measured 52.70 seconds and 1.1% of the 113.02-second publication, if saved CPU transferred one-for-one to elapsed time. The trial measured receiver calls and ended at continuation. [Dense recording history and lane count](differential-fold.md) · [Installed v3 stage clocks](first-55/stage-clocks.csv)

The parity trick depends on the frozen full-rate score taking the smaller of two normalized groups. The lag timing statistic adds eight normalized correlations. Timing candidates share the same FFT work, and the full-rate parity bound offers no early termination for a timing bin there. Individual carrier bins also share each FFT. The earlier certified carrier-row experiment had ideal modeled savings of only 3.2–5.7% of the carrier FFT stage, which is itself a small part of acquisition. The full-rate numbers above leave input, shared scout work, cancellation, original-sample verification, position solving and publication outside their savings estimate. [Separate carrier FFT budget](carrier-fft-bound.md)

## Measured prototype runtime

Five paired repeats alternated native call order per lane. The two toggle builds have byte-identical `.text` sections and differ in the default value of the experimental switch. The installed receiver comparison also includes the cost difference between the original profile-guided timing object and the experimental compilation. The recorded durations cover the complete native receiver call with initialized plans and exclude I/Q reads, continuation and publication. [Paired CPU and elapsed measurements](measurements/refine-bound-timing.json)

| Slice and control | Median native CPU | Median native elapsed | Paired CPU change |
|---|---:|---:|---:|
| Weak, v3 → enabled | 139.34 → 144.82 ms | 139.38 → 144.87 ms | +4.24% (+3.77% to +4.75%) |
| Weak, disabled → enabled | 148.49 → 144.91 ms | 148.52 → 144.95 ms | −2.18% (−2.74% to −2.01%) |
| Dense, v3 → enabled | 264.43 → 275.78 ms | 264.54 → 275.92 ms | +4.81% (+4.00% to +5.64%) |
| Dense, disabled → enabled | 289.79 → 283.97 ms | 289.94 → 284.09 ms | −2.15% (−2.97% to −1.17%) |

Twelve component tests passed across the new and earlier bounds. They exercise safe rejection, equality, missing enclosures, an unconfirmed first seed, wrap, signed CFO and byte-exact fallback. [New component tests](../../../tests/pipeline_eval/test_receiver_refine_bound.py)

## Profile-guided build

Fresh feedback came from the original site-free recipe, with eight generated windows evaluated at both antennas and zero and nonzero mixer centers. This gives 32 calls distinct from the saved weak and dense replay windows. Each object used its own counters and the archived GCC flags, with missing feedback and coverage mismatches treated as compiler errors. The stock build reproduced the installed receiver and reference timing object byte for byte. The profile-guided guard preserved every original exported symbol, all 138 factors and the continuation selection. [PGO build and timing receipt](measurements/refine-bound-pgo.json)

| Slice and control | Median native CPU | Median native elapsed | Paired CPU change |
|---|---:|---:|---:|
| Weak, installed v3 → guard | 144.56 → 141.21 ms | 144.61 → 141.26 ms | −2.00% (−3.31% to −1.54%) |
| Weak, fresh v3 → guard | 145.99 → 141.23 ms | 146.05 → 141.27 ms | −3.20% (−3.68% to −2.25%) |
| Dense, installed v3 → guard | 260.80 → 254.13 ms | 260.91 → 254.22 ms | −2.56% (−3.11% to −2.25%) |
| Dense, fresh v3 → guard | 252.66 → 247.29 ms | 252.73 → 247.39 ms | −2.13% (−2.28% to −1.87%) |

Five alternating paired repeats showed less than 1.1% variation between the two identical stock libraries. Applying the measured dense gain linearly to 13,530 lanes projects about **0.94 seconds** of native receiver CPU saved. This experiment did not measure the elapsed gain through capture, solving and publication.

The guard receiver SHA-256 is `7ac6de98302ce65c52fdad2f630094e14ab4c503999ba9f3695be2c4403a51b1`. For a publication comparison, place the verified library as `receiver.so` in an isolated copy of the installed v3 payload. Set the copied candidate specification's `detector`, `detector_sha256` and `sources["receiver.so"]` to that path and digest. Load the candidate publication module from the same copied payload so the sparse-ranking check sees the pinned receiver in its expected location. The normal acquisition loader then verifies the detector and records its new provenance. [PGO build runner](receiver_refine_pgo_trial.py)

## Reproduce

The runner relinks the archived reference and verifies the installed v3 digest before using any saved windows. Use the capture account for the authenticated DS30-0008 reader and a single Gauss CPU. Each command is bounded to fewer than 50 seconds of compute after acquiring the shared lock.

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
archive="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 45s "$@"
}
receiver() {
  lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
    -m tools.pipeline_eval.variants.experimental.receiver_refine_bound \
    "$bench/receiver-fractional-exact-v1" "$1" "$release/assets" "$archive" "$binding" \
    /srv/bulk "${@:2}"
}
receiver /var/tmp/leo-refine-bound-audit > /var/tmp/leo-refine-bound-audit.json
receiver /var/tmp/leo-refine-bound-toggle --pruning --repeats 5 > /var/tmp/leo-refine-bound-timing.json
lock env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_receiver_refine_bound.py \
  tests/pipeline_eval/test_experimental_receiver_refine_parity.py
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.receiver_refine_pgo_trial \
  "$bench/receiver-fractional-exact-v1" "$bench/spectral-vectors-combined-v1.json" \
  /var/tmp/leo-refine-pgo /opt/leo-algo08/algo08v3/payload/receiver.so "$release/assets" \
  "$archive" "$binding" /srv/bulk > /var/tmp/leo-refine-pgo.json
```
