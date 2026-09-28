# Refinement-cache review

This review concerns one invocation of `leo_full_search_run` on one 20-ms
receiver/probe window. The goal is memoization of repeated refinement work while
retaining every original candidate entry, its coarse fields, and the existing
final ordering. It is not candidate deduplication.

## Exact dependency keys

`fine_scores` depends on the refined epoch and the immutable per-run search
state (samples, count, rate, templates, fine-frame/symbol configuration, and
acquisition origin). It does not depend on the retained coarse CFO. Its returned
score vector does depend on the requested FFT-bin interval:

```
fine-result key = (run generation, refined_epoch, first_bin, bin_count)
```

Use the integer FFT-bin identity after the existing `nearbyint` and circular
mapping, rather than a newly rounded frequency double. The candidate still uses
its own original 160-kHz coarse-bin range, tie handling, parabolic interpolation,
and resulting `fine_cfo_hz`.

The conditioned result cannot be keyed only by epoch. Its local phasor anchor,
regular-grid decision, FP32 screen, guard, exact rechecks, and winner all depend
on the exact 100-Hz grid produced after fine interpolation:

```
conditioned-result key = (run generation, refined_epoch,
                          exact grid start, nf, grid step/mode)
```

For the present generator, an exact start and `nf` with the fixed 100-Hz step
identify the grid. Store or verify the generated grid identity rather than
assuming that two numerically close interpolation results are equivalent.

Fused verification and final GLRT both depend on epoch and the exact acquired
CFO selected by the conditioned stage:

```
verification key = (run generation, refined_epoch, acquired_cfo_bits)
GLRT key         = (run generation, refined_epoch, acquired_cfo_bits,
                    offset=+0 bits, frame_limit=16, final_scoring=1)
```

Their three-result vectors may be copied to each matching candidate, while
candidate-specific coarse epoch, coarse bin, coarse score, fine score, and
conditioned metadata remain separate. A matching GLRT result still sets
`glrt_complete` on every candidate entry.

## Lifetime and floating-point discipline

Keep caches inside one search call and invalidate them before each new `ingest`.
Neither samples nor scratch arrays are immutable across receiver/probe windows;
a workspace is deliberately reused by the cohort runner. Include a per-run
generation in every key if cache storage lives in the workspace.

Use a copied `uint64_t` representation for cache-key doubles, not `==` or a
numeric tolerance. That treats `+0` and `-0` as distinct and declines reuse for
different NaN payloads. Candidate-derived CFOs should be finite; reject or
preserve the pre-existing error path for nonfinite values rather than allowing a
NaN key to match accidentally. The stricter bit key may miss a harmless reuse,
but it cannot alter floating-point selection through a tolerance or signed-zero
normalization.

Memoize only completed output vectors. The scoring routines use mutable
workspace buffers (`base`, `input`, `weighted`, FFT buffers, and GLRT rotations),
so cache entries must own copied scalar/vector results, never pointers into
those buffers. A cache hit must be safe even though it leaves the previous
routine's scratch contents in place; each subsequent stage must initialize all
scratch state it reads. Test hit/miss interleavings, not just all-miss parity.

## Fine FFT union opportunity

For duplicate refined epochs, build the union of their *original* initial fine
bin intervals. Transform input once per epoch/frame, then read each candidate's
original interval from that transform and retain its original frame and bin
addition order. A contiguous union can avoid repeated output-range work when a
range-aware backend is available. It must preserve circular-bin handling and
must not widen a candidate's `fine_scores` search when choosing its winner.

Do not compute every fine bin merely because several candidates share an epoch:
when ranges are disjoint, the union is the bounded work floor. Conversely, the
current default adapter performs the whole transform already, so a range union
alone may remove no transform cost; measure only after an implementation.

## Ordering, multiplicity, and error handling

Keep the retained-peak loop and its candidate insertion order unchanged.
Populate every candidate before the existing `full_candidate_before` insertion
sort; cache hits must copy identical stage fields before that sort. Execute or
copy GLRT after the same sort, preserving its existing result order. Do not
collapse two candidates that share an epoch or even an acquired CFO: their
coarse identity and score are evidence-bearing fields.

If a stage fails, retain the original fail-fast behavior. Do not cache a partial
score vector or convert an error into a miss/fallback. Report cache multiplicity
separately from candidate count: eight candidate entries can require fewer
unique fine epochs, fewer exact conditioned grids, and fewer final `(epoch,CFO)`
keys. Candidate-object parity against the full control remains the required
qualification; cache hits do not make this an approximate optimization.
