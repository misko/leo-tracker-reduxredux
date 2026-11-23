# Eight-second support knots triggered the fine-bank fallback

The midpoint sentinels rejected the eight-second ECEF Hermite approximation on the genuine short DS30-0016 saved packet. The maximum sentinel velocity error was **0.12568 m/s** against the frozen **0.035 m/s** tolerance. The exact fallback reproduced the archived early regional decision. Including the attempted approximation and fallback increased measured proof CPU from **174.64 ms to 183.80 ms**. [Frozen comparison](regional-orbit-interpolation-protocol.md) · [Measurement](measurements/regional-orbit-interpolation.json)

The original horizon screen propagated the complete 11,181-orbit catalogue at its original knots and selected the same 552 satellites. The candidate's fine bank propagated six support knots and five midpoint sentinels, compared with 38 native one-second knots per satellite. The final five-second interval ended at its prescribed exact boundary. The proof used the original lattice, mixture weights, phase preparation, fused observer kernel and terminal policy. The two timed proofs both visited the same 24 points and returned `eligible_exterior_separation`, leaving inference eligible. The saved run ended before cold ranking, position fitting or publication. [Original physical candidate](weak-combined-raw.md)

## Approximation before fallback

The off-clock comparison tested ECEF state error at every original fine knot and used the original likelihood on all 96 geographic points. This was a diagnostic for the rejected approximation. The exact fallback did no additional work for these comparisons.

| Measure | Maximum or changes | Frozen limit |
|---|---:|---:|
| ECEF position norm | 0.06290 m | 0.30 m |
| ECEF velocity norm | 0.12568 m/s | 0.035 m/s |
| Reference-frequency difference | 2.41470 Hz | 1.0 Hz |
| Phase-tangent difference | 1.54992 Hz/s | 2.0 Hz/s |
| Pooled or per-receiver score difference | 0.0004625 | 0.003 |
| Horizon sign changes across 15,526,656 orbit-time cells | 0 | 0 |
| Owner-vote changes across 1,248 track votes | 0 | 0 |
| Usable satellite label changes | 0 | 0 |

The approximation failed the velocity and reference-frequency gates despite reproducing the terminal verdict and probe sequence. The sampled position error at the midpoints reached 0.02001 m. It missed the larger 0.06290 m position error elsewhere on the original bank, illustrating why these sentinels do not certify unsampled times. No interpolation extended beyond either exact endpoint.

## Timing boundaries

| Proof operation | Exact CPU | Guarded candidate CPU |
|---|---:|---:|
| Original horizon propagation and ECEF conversion | 32.13 ms | 32.45 ms |
| Fine bank, including charged fallback | 5.33 ms | 8.34 ms |
| Original phase geometry | 27.26 ms | 31.17 ms |
| Terminal scoring and decision | 93.18 ms | 95.59 ms |
| Complete proof | 174.64 ms | 183.80 ms |

The guarded fine-bank clock includes 1.73 ms for support and sentinel SGP4/ECEF, 1.15 ms for interpolation and checks, and 5.32 ms for the exact fallback. The complete proof elapsed times were 174.70 and 183.81 ms. Allowing all other stages to run at the exact control pace, the measured fine-bank change added 3.01 CPU ms. The original fine-bank CPU was only 5.33 ms, about 3.1% of the exact weak proof, even if a hypothetical replacement were free. These are single-pair timings on one site. The audit provides no dense or end-to-end timing estimate.

Existing Hermite code uses previously paid SGP4 supports to evaluate receiver or session shapes at arbitrary times. The original regional proof uses a linear phase stencil over its already propagated one-second states. This experiment changed how the states in that one-second bank were generated and left the downstream stencil in place. The fixed cadence, velocity rule and tolerances were selected before the measured replay. One initial invocation rejected equivalent input-region classes at preparation, before it reached either proof. The comparison now checks the handoff's center and width explicitly. The focused interpolation, orbit-audit and catalogue-handoff tests passed together, 13 tests. [Existing receiver interpolation](../../../tools/pipeline_eval/reference/grid.py) · [Exact setup audit](live-orbit-setup-audit.md)

To reproduce from the repository root, use the shared locked slot and a fresh output path.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  timeout 30s "$release/venv/bin/python" -BPs \
  reports/ALGO08/v3/regional_orbit_interpolation.py /var/tmp/regional-orbit-interpolation.json
```
