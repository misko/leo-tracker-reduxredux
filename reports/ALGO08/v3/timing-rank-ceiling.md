# Rank ceiling for the released known-pilot timing bank

A fixed dense basis for all eight lag correlations misses the **3.49 CPU-second** dense saving target under the frozen cost model. The most favorable priced rank is **61**, which can capture at most **4.03%** of the lower pilot edge's operator power and **4.09%** of the upper edge's. To capture even half needs at least rank **1,154** and **1,156**, respectively. The full 20 ms and short 12 ms constructors produced byte-identical filter banks on each edge. The frozen stopping rule triggered before any saved waveform was opened. [Protocol](timing-rank-ceiling-protocol.md) · [Receipt](measurements/timing-rank-ceiling.json.gz)

| Pilot edge | Algebraic rank lower bound out of 3,333 | Rank lower bound for 50% power | 90% | 99% | Power ceiling at rank 61 | Power ceiling at rank 22 |
|---|---:|---:|---:|---:|---:|---:|
| Lower | 3,271 | 1,154 | 2,601 | 3,069 | 4.034% | 1.625% |
| Upper | 3,271 | 1,156 | 2,601 | 3,069 | 4.089% | 1.678% |

## Native operator and certificate

At quarter rate the ordinary scout forms eight lagged products, summing the products of the two modes of the same lane. The lags are 2, 4, 6, 11, 18, 28, 44 and 74 samples. Each stream has `4,740 − lag` live input cells and is zero-padded to 4,800. The released kernel Fourier-transforms the stream, multiplies by a conjugated, normalized pilot-lag spectrum, inverse-transforms, and takes 3,333 epochs. It adds each squared correlation divided by the corresponding sliding input energy, then applies circular exclusion to find the 12 timing peaks. The analysis uses the stored binary32 timing multipliers from both actual constructors. [Native accessor and certificate](timing_rank_ceiling.py) · [Original timing-only oracle](timing-only-oracle.md)

Let `H_l = U* diag(F_l) U` be that lag's circulant with unitary DFT `U` and stored multiplier `F_l`. Let `R` restrict the epochs and `P_l` embed the `W_l` live input columns in the padded array. Concatenate `A_l = R H_l P_l` to form `A`, with an independent formal input stream for each lag. For `M = 3,333` and `N = 4,800`, the total squared Frobenius norm is at least `sum_l (M + W_l − N) sum_k |F_l[k]|² / N`. Before removing input columns, each retained row has the same energy by translation. Removing `N − W_l` columns costs at most one full padded column's energy each.

For any orthogonal projector `Q` of rank `r`, allowing all padded input columns can only increase `||QA||²_F`. In this enlarged problem the squared norm is `sum_k λ_k q_k` with `λ_k = sum_l |F_l[k]|²` and `q_k = ||Q R U*[:,k]||²`. These leverages sum to `r` and each is at most `M/N`. Assigning this mass to the largest `λ_k` first gives an upper bound for every fixed rank-`r` output span. Dividing by the trace lower bound gives the retained-power ceiling. A single lag also bounds the joint algebraic rank from below by its count of nonzero Fourier bins minus the rows and columns removed. Both edges give 3,271 by this argument. Each binary32 component is converted to exact integer multiples of `2^-149`. Powers, rank thresholds and leverage allocations use integer or rational arithmetic. Component tests cover binary32 reconstruction, equality on a flat full circulant and a small explicit Hermitian eigensolve on restricted circulants. [Tests](../../../tests/pipeline_eval/test_timing_rank_ceiling.py)

## Price against the original timing opportunity

The prior four-row oracle projects 4.496 CPU s of gross savings on 13,530 dense lane calls, before estimating a single row. Saving 3.490 CPU s leaves 74.35 µs per lane, or 67.98 µs per scout at the observed 105 scouts per 96 lanes. Even at 24 billion complex products per second, evaluating eight direct rank dot products at each of 3,333 epochs fits rank 61 with free input preparation. A second calculation charges 43.30 µs for eight short-path forward FFTs at the archived median per-transform cost. It leaves 24.68 µs and fits rank 22. There is no charge here for normalization, ranking or stock fallback. Direct eight-output synthesis at the lower edge's half-power rank alone would cost at least 1.28 ms per scout under this same throughput assumption. Even a single isolated lag requires rank 566–618 for half its own power across the two edges, above the generous one-dot budget of 489. [Four-row savings and scout counts](timing-only-oracle.md) · [FFT clocks](sample-major-fft.md)

The certificate measures uniform linear operator power over formal lag inputs. The received lag streams are correlated quadratic functions of the two modes, timing scores use a received-energy denominator, and the receiver selects ordered peaks. Preserving operator power does not establish which rows survive on a physical capture. The result rules out the priced dense direct synthesis at the frozen half-power criterion. Structured evaluation of fewer rows, signal-dependent sparse or nonlinear nominations, and other uses of translation symmetry remain outside this bound. No receiver, localization or RF accuracy result was generated.

## Reproduce

The first attempt stopped at the full receiver digest check before native extraction. The installed path held a different object. The sealed run read the archived, byte-verified full receiver relink `2258f592…` and the archived short receiver `06570a53…`, alongside the pinned original pilot assets. Both archived relinks were already available from the group receiver study. The raw receipt SHA-256 is `67aac1d2a99a4c2d5cad22c618a05e09496518780a5abda986c05ea2cb9d780a`. Construction and extraction took 0.54–0.99 ms CPU per edge and aperture. Each exact bound and its eight single-lag checks took 34.95–35.71 ms CPU. [Archived relinks](whole-group-receiver-bound.md)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
run=$(mktemp -d /dev/shm/leo-v3-rank.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/src:$PWD/reports/ALGO08/v3" timeout 45s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.timing_rank_ceiling "$run/native"
```
