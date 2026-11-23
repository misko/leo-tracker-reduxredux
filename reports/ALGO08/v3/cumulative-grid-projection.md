# Exact Graph and grid projection in active cumulative publication

The combined opt-ins reproduced both complete saved publications, including every original score and official image. Through process exit, DS30-0016 improved from **5.511 to 5.452 s elapsed**. Dense DS30-0008 went from **26.926 to 27.036 s**. This pair does not establish a dense publication speedup. [Frozen protocol](cumulative-grid-projection-protocol.md) · [Receipts through process exit](measurements/cumulative-grid-projection.json.gz)

The control uses the installed Graph and the existing cumulative solver, exact cold rows, prepared predictive geometry, checked posterior and explicit-layout renderer. The combined run adds ordered Graph edge construction, exact best-piece reuse, fused observer projection and selected curved row packing. The latter two are enabled with a verified library supplied by path. Both launches use `publish_active`, the same active entry as the cumulative receiver CLI. The trial reads the existing detector document and signed inventory to supply one verified handoff.

| Stage | Weak installed → combined (s) | Dense installed → combined (s) |
| --- | ---: | ---: |
| Complete Graph preparation CPU | 0.066 → 0.031 | 1.459 → 0.929 |
| Standard numerical evidence CPU | 0.245 → 0.202 | 5.671 → 5.634 |
| Full scientific solve CPU | 2.645 → 2.555 | 22.792 → 22.868 |
| Render and encode CPU | 1.186 → 1.261 | 2.355 → 2.349 |
| Complete saved publication CPU | 5.212 → 5.161 | 26.680 → 26.785 |
| Fresh process CPU | **5.506 → 5.449** | **26.905 → 27.027** |
| Fresh process elapsed | **5.511 → 5.452** | **26.926 → 27.036** |

The dense Graph reduction was **0.530 CPU s**. Dense standard evidence was **0.037 CPU s** faster. The installed timers recorded **3.826 → 3.742 CPU s** for the curved callbacks and **1.119 → 1.175 CPU s** for reduced predictive integration, with 356 checked posterior exports in both processes. The signed refit preceding the map took 0.559 s in the control and 0.806 s in the combined process. These are measured stage differences in a single pair. The earlier dedicated map replay measured a **0.358 s** map improvement with a reconstructed fit. The complete publication result takes precedence for this composition's timing. [Selected-context experiment](grid-feature-projection.md) · [Earlier Graph-only publication pair](cumulative-dense-graph.md)

## Original outputs

The weak input was the genuine DS30-0016 candidate packet from matched-cost run `-01`. It retained 116 owner and role rows per arm, the original RF RMS of 121.526 / 120.291 Hz and the original region and causal archive. DS30-0008 retained 4,367 owner and role rows per arm and RF RMS of 140.961 / 140.950 Hz. Both controls and both candidates matched their respective archived signed terminals, arm positions, original geographic verdicts, numerical path and complete 179-point grid in each arm. All paired PNGs match as bytes and independently decoded RGBA arrays. Every run also matches its pinned original explicit-layout image hashes. Both sidecars bind the actual position PNG and retain the original numerical content.

Each candidate used 356 native selected designs and 712 native projections, including four checks against the stock projection arrays for the four private phase views. Every map used 356 independently reduced predictive integrations. The Graph kept all 4,137 ordered edges and 13 tracks on weak and all 90,746 edges and 208 tracks on dense. Weak reused 91 of 120 best-piece calls and dense reused 1,509 of 2,794. Graph, grid-kernel and geographic fallbacks were zero in both candidates. Both controls used the incumbent grid projection and packing by design.

## Run boundary

Four fresh processes exited with status zero. The retained weak pair ran installed first. The dense pair ran combined first after weak parity passed. All launches used one Gauss CPU under the shared low-priority lock and private tmpfs, with zero waveform calls and zero reported dependency input blocks. An initial weak control completed before the separate verifier hit the historical store's older read-only API. The retained pair uses the repository verifier and fresh roots, while the isolated worker still loads the same installed solver.

The active route verifies the library digest and supported CPU before loading. It keeps the original sampler for unsupported layouts and mapped grids, and keeps the original projection after a view fails validation or produces nonfinite native results. These guards run within the opt-in. Forty-one component and adjacent tests passed. [Active entry](unified_short_bootstrap.py) · [Native binding](grid_feature_projection.py) · [Trial driver](cumulative_grid_projection.py)

## Reproduce

Use a permitted local account for the sealed archive, with an existing private tmpfs directory as `$output`. The parent verifier imports the current repository storage contract; the isolated children pin the installed solver. The library hash is `7ac9f74eb08d1992bde8738dbc8f6ec9687eb7fe4f5d5f4ae3301ddfa061d0fb`.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
export PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release"
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 "$@"
}
locked cc -std=c11 -O3 -march=haswell -fno-fast-math -fno-math-errno \
  -ffp-contract=off -shared -fPIC -Wall -Wextra -Werror \
  reports/ALGO08/v3/grid_feature_projection.c -lm -o "$output/projection.so"
locked "$release/venv/bin/python" -BPs reports/ALGO08/v3/cumulative_grid_projection.py \
  weak "$output/weak" "$output/projection.so"
locked "$release/venv/bin/python" -BPs reports/ALGO08/v3/cumulative_grid_projection.py \
  dense "$output/dense" "$output/projection.so" --after-weak "$output/weak/result.json"
```
