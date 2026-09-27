# Rank-to-acquisition reuse in the stable FP32 blind detector

This is a source audit of the stable one-confirmation FP32 FFTW detector. It
does not modify or benchmark the detector. The narrow conclusion is:

> The selected window's native lag-4 fold is exactly reusable only when tone
> nuisance fitting does **not** alter the working samples. Even on eligible
> calls it replaces only the differential half of coarse folding; the folded
> power statistic and the different coarse projection still have to run.

No patch is recommended for the 10x work. The compatible fragment is real, but
its maximum measured stage ceiling is small and the current rank workspace no
longer holds the selected window's fold after all six windows are ranked.

## Frozen implementation examined

The stable candidate is `fft32/libfft32_fftw.so`, SHA-256
`3fcdefd955725d5501b4cd5e577511c0b305e808613f7a30c2b77b382357b8a0`.
Its build receipt pins the current authoritative `dwell.c`, `window_rank.c`,
`coarse_differential.h`, `ci16_fold.h`, `tone_nuisance.h`, and `presence.c`
bytes. The source hashes still match the receipt. The FFT backend changes
transform arithmetic to FP32 FFTW; it does not alter the rank or fold source.

The wrapper first ranks all six 20 ms windows directly from the natural-stride
dual-RX CI16 visit, then packs only the selected window and invokes the
unchanged confirmation API
([blind_strided_v4.c:151](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds5_cached_tracking/native/blind_strided_v4.c:151)). The stable transfer result retained 129/129 new-development reference positives with no selected-window or rank-order changes. Its complete caller cost was 490.922 ms over 256 receiver-visits, or 1.620x relative to its independent packed FP64 reference. That result does not isolate the fold proposed here.

## Exact compatibility

Under the frozen profile, the rank and selected-window coarse stages share the
following geometry:

| Property | Six-window rank | Selected-window coarse differential | Compatible? |
|---|---|---|---|
| Source interval | one 20 ms slice at a time | selected 20 ms slice | Yes for the selected slice |
| Frame starts | 15 values, `nearbyint(frame*rate/750)` | loop limit 16, but frame 15 starts exactly at the 20 ms count and is rejected | Yes: both consume frames 0..14 |
| Frame cell count | `n=nearbyint(rate/750)` | same `n` | Yes |
| Lag | hard-coded 4 | frozen `DIFFERENTIAL_LAG=4` | Yes only for this profile |
| CI16 product | exact int64 `b*conj(a)` | exact int64 `b*conj(a)` | Yes |
| Per-cell support | `min(n, window-start-4)` | same bound through `paired` and `diff_support` | Yes |
| Normalization | divide lag sums by support in FP64 | divide lag sums by `diff_support` in FP64 | Yes |
| Input state | original recorded CI16 | original CI16 only when nuisance is not applied | Conditional |

The natural-stride rank implementation performs the same real and imaginary
integer products as the packed CI16 fold
([blind_strided_v4.c:13](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds5_cached_tracking/native/blind_strided_v4.c:13)). Packing changes layout, not values. The authoritative packed fold widens each CI16 product before accumulating and stores exact int64 sums
([ci16_fold.h:9](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/ci16_fold.h:9)). Both paths remain below the documented 2^36 bound.

The rank's dense native fold is available because the frozen hybrid projection
sets `RANK_FULL_FOLD`. It divides every native cell by the fixed support before
projection
([window_rank.c:234](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:234)). Coarse differential divides by the same lag support before centering
([coarse_differential.h:96](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:96)). Therefore the uncentered normalized complex lag array is numerically reusable on an unmodified selected window.

## Why most computation is not reusable

### Nuisance ordering is a hard boundary

Confirmation first converts the packed CI16 window to FP64 complex samples,
runs tone nuisance handling, and only then runs coarse acquisition
([presence.c:934](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:934),
[presence.c:743](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:743)). The nuisance model estimates a tone from the full selected window and may subtract it in place
([tone_nuisance.h:6](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/tone_nuisance.h:6)).

When no fit is applied, `execute()` passes the original CI16 pointer to coarse
folding. The cached rank lag fold is then identical. When subtraction is
applied, `execute()` deliberately passes `NULL`, and coarse folding recomputes
from the modified FP64 samples
([presence.c:749](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:749)). Reusing the raw rank fold in this branch would silently undo the nuisance model and change window confirmation. Moving nuisance before six-window rank would also change rank scores and selected-window ordering.

The nuisance transform itself is not reusable. It is an FFT of raw selected
samples plus full-window energy, three long lag sums, a least-squares amplitude,
and possible subtraction. Rank has a 512-point transform of a folded lag-4
sequence. The transform inputs and meanings differ.

### Coarse needs power as well as lag

`coarse_fold_ci16()` accumulates both sample power and lag-4 products. Coarse
then centers both native arrays. Its local native score is the normalized lag
correlation plus a weighted normalized power correlation
([coarse_differential.h:46](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:46)). Rank computes no folded-power array. An exact reuse path must still make a complete selected-window pass to compute power with the original support and accumulation order.

### Projection and search are different

Rank projects the native fold to 512 cells, evaluates two hybrid projection
statistics, and retains one timing peak per window
([window_rank.c:310](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:310)). Coarse differential projects the selected fold to 4,096 or 8,192 cells, performs a separate correlation, selects up to eight separated neighborhoods, and rescales them at native resolution
([coarse_differential.h:110](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:110)). The rank FFT, projected arrays, score, and selected epoch cannot replace this computation without changing search coverage and the statistic.

## State and memory obstacle

After the six-window rank loop, `rank->folded` contains the fold of window 5,
not necessarily the selected window. The selected projection family is itself
chosen only after all six windows have been compared
([window_rank.c:355](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:355)). Exact reuse would require either:

- caching all six normalized native folds: about 312.5 KiB at 2.5 Msps and
  625.0 KiB at 5 Msps; or
- caching the current best fold separately for each of the two projection
  families as ranking proceeds: about 104.2 KiB at 2.5 Msps and 208.3 KiB at
  5 Msps, plus up to six native-array copies per family.

Refolding the finally selected window avoids this storage but is the duplicate
work the proposed change is meant to remove.

## Measured ceiling

The available fine-grained receipt is the earlier common-profile blind-cost
diagnostic, not the stable FP32 transfer run. It reports median selected-window
coarse CPU of 0.229 ms at 2.5 Msps and 0.539 ms at 5 Msps. Complete caller
medians were 1.554 and 3.303 ms; native dwell medians were 0.971 and 2.055 ms.

Even deleting the **entire** coarse stage, which this reuse cannot do, would
bound that receipt's improvement to:

| Rate | Whole caller ceiling | Native dwell ceiling |
|---|---:|---:|
| 2.5 Msps | 1.173x | 1.309x |
| 5 Msps | 1.195x | 1.355x |

Actual reuse saves less because it applies only on nuisance-unmodified calls,
still reads the selected window for folded power, and still performs coarse
centering, projection, FFT, peak selection, and native power refinement. The
stable FP32 backend also already reduces transform cost, so the older absolute
stage milliseconds must not be subtracted from its 490.922 ms result or
presented as a paired FP32 prediction.

This ceiling is useful only to reject the change as a 10x route. It is not an
ARM estimate and does not establish the speed of a hypothetical patch.

## Patch decision

Do not patch the frozen detector for this experiment. A scientifically exact
implementation would need all of the following:

1. cache the selected projection family's native normalized lag fold during
   ranking, with rate, `n`, lag, source-window, receiver, and unconditioned-CI16
   identity attached;
2. run tone nuisance unchanged;
3. consume the cache only when `nuisance.applied == 0` and every identity field
   matches;
4. add a power-only exact CI16 fold that preserves the current power support and
   integer accumulation order;
5. continue the existing coarse centering, projection, peak selection, local
   power-plus-differential scoring, fine CFO search, and exact/control GLRT; and
6. prove equality of the normalized lag array, coarse grid, selected candidate,
   all scientific outputs, nuisance receipt, and input immutability, including
   tone-applied fallback.

That patch is feasible but not material to the measured 10x deficit. It adds a
conditional internal contract, cache copies, and a second fold mode to remove
only one arithmetic component of a stage whose complete removal was worth at
most about 1.20x at the caller boundary in the available stage receipt. It
should be reconsidered only after a future profile shows this exact duplicate
lag fold is a dominant cost in the target backend.
