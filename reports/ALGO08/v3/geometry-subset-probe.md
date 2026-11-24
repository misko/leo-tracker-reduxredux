# Geometry-selected epochs for cold association

Four geometry-selected epochs with a 16-satellite shortlist retained every original winner, ungated nominee and compatible satellite across 2,416 saved cold-association requests. Eight epochs also retained them all. With exact shortlist rescoring, the conservative fallback added **0.561 CPU s on dense DS30-0008** and **0.195 s on medium DS30-0316** for four epochs. Even if a free oracle identified every safe omission, those four-epoch savings would be only **0.204 s** and **0.065 s** on the same scoring work already accelerated by exact catalogue blocks. These results end the proposal before finalist fitting. [Frozen protocol](geometry-subset-probe-protocol.md) · [Saved measurements](measurements/geometry-subset-probe.json.gz)

## Real-epoch shortlist recall

The experiment used the 1,476-orbit causal catalogue, original saved detector packets, signed RF values and original search states. At each state, it used the released nominal or phase-shifted Doppler and elevation prediction at the actual observation epochs. The released orbital bank uses its existing interpolation. The experiment introduces no quadratic Doppler approximation. Epoch selection used time and the demeaned, normalized Doppler from 16 catalogue alternatives at deterministic NORAD ordinals. The earliest point starts an ordered farthest-first traversal of these features. The two budgets use its first four or eight distinct observation epochs. Only the sparse score uses the observed CFO. The original white profile, all-epoch horizon and track gates were reapplied to geometry-shortlisted rows. [Runner](geometry_subset_probe.py)

| Case | Original calls | Original compatible instances | Geometry 4 missed chosen / ungated / compatible | Geometry 8 missed chosen / ungated / compatible | Uniform 4 missed chosen / ungated / compatible | Uniform 8 missed chosen / ungated / compatible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 dense | 1,792 | 499 | 0 / 0 / 0 | 0 / 0 / 0 | 4 / 4 / 0 | 0 / 0 / 0 |
| DS30-0316 medium | 624 | 153 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

The pinned stock driver reproduced the complete ordered original ranks on both captures. For all four shortlist rules, every track, orbit index, NORAD and full-row signed alias in each of the seven dense finalists (112 rows per finalist) and six medium finalists (39 rows per finalist) was present in at least one shortlisted tape state. This condition permits recovery but does not establish that an altered search can assemble those branches. The uniform four-epoch misses show why the pooled finalist witness is weaker than per-state recall. The shadow scorer always returned the stock array to discovery, so branch changes and untaped states remain unmeasured. [Original exact controls](cold-exact-budget.md)

The released radio horizon uses nonnegative elevation at every track epoch. Sampled horizons admitted zero false-visible rows on these two tapes. Neither this predicate nor the experiment tests a separate solar-eclipse rule. Four and eight geometry epochs changed the sparse signed alias on respectively **415 and 220** of 30,464 retained dense instances and **102 and 23** of 10,608 retained medium instances. The original chosen satellite's sparse alias never changed. No tested sparse mean was within the predeclared error interval at the alias half-period boundary. Even away from that boundary, using a different set of measurements can change the mean enough to round to another alias. The all-epoch rescore recalculates that alias and its bias independently. [Per-rule counts](measurements/geometry-subset-probe.json.gz)

## Cost including original replays

| Case | Epochs | Stock curve CPU | Selection + sparse + exact rerank CPU¹ | Original full replays | Changed compact diagnostics | Hindsight net saving | Conservative net saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 | 4 | 0.947 s | 0.742 s | 1,300 / 1,792 | 1,092 | +0.204 s | −0.561 s |
| DS30-0008 | 8 | 0.947 s | 0.775 s | 1,226 / 1,792 | 1,101 | +0.171 s | −0.590 s |
| DS30-0316 | 4 | 0.325 s | 0.260 s | 430 / 624 | 401 | +0.065 s | −0.195 s |
| DS30-0316 | 8 | 0.325 s | 0.270 s | 420 / 624 | 401 | +0.055 s | −0.207 s |

¹ Includes the branch's checked white-profile domain and exact survivor horizon. It holds the original initial orbit-plane and full projected Doppler gather costs fixed. The existing full plane was already available on the tape, so the experiment establishes no saving in its propagation or construction. The proxy touched 10.58 / 21.16 million dense prediction cells and 3.67 / 7.35 million medium cells at four / eight epochs. Exact shortlist scoring touched another 1.33 million dense and 0.50 million medium cells on either budget.

The hindsight model knows which original rivals are required and trusts all other omissions and compact arithmetic at zero verification cost. The conservative accounting requires the sampled residual contrast to make each omitted visible rival both too expensive to win and unable to pass the all-time RMS gate. Pairwise contrasts cancel the unknown constant and integer alias, and the bound pads rounding and minimizes over the omitted observations. The exact shortlist supplies an independently evaluated visible upper bound. The replay estimate charges every call unresolved by this proof or whose compact array changed an original diagnostic. The latter check uses the stock answer in the shadow. A deployment would need verified same-layout arithmetic or original full scoring for uncertain calls. This is a priced fallback policy using observed operations, not a measured end-to-end optimization. [Contrast proof](representative_contrast_bound.py)

The earlier moments trial approximated the predicted Doppler curve and lost the dense branches before full-row reranking. This experiment removes that approximation and finds a fixed shortlist with full recall on the tapes. The earlier representative contrasts screened original rows by a necessary inequality and sent every unresolved row to exact scoring. Here the geometry-sensitive choice and fixed top-16 proxy run first, with a separate price for proving that this shortlist is sufficient. The current exact catalogue-block pair already saves 0.384 s on this dense rank and 0.113 s on medium while preserving every complete rank node bit for bit. The shortlist clocks cover overlapping curvature-association work and give no extra speed credit to that pair. No final accuracy claim follows from these observations. [Time-moment failure](track-moment-exact-rescore.md) · [Representative contrasts](full-family-amortized.md) · [Exact block pair](catalogue-block-bound.md)

## Projecting selected times before scoring

G4 is independent of observed residuals and depends on the causal catalogue and trial phase. Computing its epoch choice from scratch still needs the 16 training rows at every original track epoch in each state. That is 1,253,376 dense and 468,224 medium training prediction cells before deduplication. The remaining rows could be projected at selected times first and their retained or unresolved rows expanded later. The actual cost of sharing those projections across tracks and fallbacks is unmeasured. The per-track epoch choices may overlap at common timestamps, making a simple cell-proportional cost model unreliable.

The saved dense profile gives a generous disjoint ceiling above the tested curve. Association took 1.672791 CPU s, of which the original curve took 1.051819 s. The remaining **0.620972 s** includes **0.164923 s** of shifted prediction and **0.456049 s** for all other work, including gathers, gates, diagnostics, nomination and reassembly. A separate dense attribution priced the corresponding remainder at **0.505273 s**, split into 0.162079 s of prediction and 0.343195 s of other work. Crediting all 0.621 s for free, including the mandatory operations in that scope, would take the conservative G4 result from −0.561 s to at most **+0.060 s** and the hindsight G4 to **+0.825 s**. A real sparse projection, survivor expansion and fallback would all spend part of that credit. These are cross-observation ceiling models, not paired stopwatch results. [Dense cold profile](measurements/cold-exact-budget-profile.json.gz) · [Independent dense attribution](measurements/dense-assignment-reuse.json)

Nominal centre and corner projection is a different scope. The saved profile counted 0.547 CPU s across 13 requests sharing five actual projections. The full nominal frequency, elevation and derivative planes also feed original receiver calibrations, full-observation frequency statistics and phase proposal statistics. Sparse association by itself leaves those consumers in place, alongside original full-row exact finalist scoring and downstream evidence. Replacing seed and phase statistics would be a different approximation and could revisit the loss of dense branches seen in the moment test. The measured ceiling and current fallback costs leave insufficient scope for a from-scratch G4 integration test. [Anchor sharing](blind-rank.md) · [Original discovery](../../../src/leo/analysis/localization_v3/discovery.py)

## Scope and reproduction

The two rank-only processes exited successfully on Gauss. Dense used 13.85 CPU s / 13.87 wall s and medium 6.85 CPU s / 6.86 wall s including runtime setup, catalogue preparation, stock ranking and all four observers. The operating system reported 2,024 / 2,184 input blocks and 0 / 10 major faults. The signed saved packets and archives were verified in tmpfs. No waveform, finalist fit, calibration fit, grid, terminal or figures were produced. Four focused component tests passed. [Sealed clocks and input digests](measurements/geometry-subset-probe.json.gz) · [Component tests](../../../tests/pipeline_eval/test_geometry_subset_probe.py)

Use freeze `d9e8561f5`, the installed release and local staged evidence pinned in the receipt, with fresh tmpfs output paths. Keep `dense` then `medium` inside one shared Gauss lock. The launch was as `leo`, CPU 2, nice 15, I/O priority 7 and one numerical thread. [Runner](geometry_subset_probe.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  bash -eu -c 'for case in dense medium; do
    timeout --kill-after=2s 45s "$1/venv/bin/python" -IB \
      reports/ALGO08/v3/geometry_subset_probe.py "$case" "${2}-${case}"
  done' bash "$release" "$new_tmpfs_prefix"
```
