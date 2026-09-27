# Repository scanner application profile

The actual `leo.scanner.detector.detect_first_glrt64` call takes about 1.6 seconds
for one 2.5 Msps 120 ms dual-receiver dwell and 4.1 seconds at 5 Msps on this
server. This is a repository scanner-analysis workload over saved DS5 IQ. It is
not evidence that the live deployed DS5 currently runs this Python path.

The two cases were selected from metadata before outcomes: the first development
case at each rate ordered by session, source counter, visit index, and case ID.
The scanner configuration used 11 overlapping 20 ms probes, two receivers, and
10 retained acquisition candidates. Numerical thread environment variables were
fixed to one and the process was pinned to P-core 0. The production coarse backend
reported `avx2_fma`.

| Rate | Uninstrumented process CPU | Uninstrumented wall | First detection established |
|---|---:|---:|---|
| 2.5 Msps | 1,558.7 ms | 1,615.5 ms | after probe 2; returned probe 0 |
| 5 Msps | 4,131.7 ms | 4,143.1 ms | not observable from this receipt; returned probe 0 |

Each uninstrumented application call was followed by a separate diagnostic pass.
The diagnostic wrappers returned exactly the same serialized `DwellDetection`.
Both cases produced 10 acquisition candidates for every one of 22 receiver-probe
calls, so each dwell performed 220 GLRT-64 confirmation scores. The 50% overlap
causes each receiver's 120 ms dwell to be presented to acquisition as 220 ms of
20 ms probe input, a 1.833x reprocessing factor.

| Inclusive stage | 2.5 Msps CPU | Share of diagnostic call | 5 Msps CPU | Share of diagnostic call |
|---|---:|---:|---:|---:|
| Complete application diagnostic | 1,535.7 ms | 100% | 4,476.2 ms | 100% |
| Symbolwise acquisition | 1,252.3 ms | 81.5% | 4,164.8 ms | 93.0% |
| Coarse folded anchor grid | 682.6 ms | 44.5% | 3,065.5 ms | 68.5% |
| Fine CFO grids | 138.8 ms | 9.0% | 303.7 ms | 6.8% |
| Conditioned CFO grids | 151.6 ms | 9.9% | 315.9 ms | 7.1% |
| Final normalized acquisition scores | 70.7 ms | 4.6% | 163.5 ms | 3.7% |
| GLRT-64 confirmation | 276.8 ms | 18.0% | 302.7 ms | 6.8% |
| GLRT correlation workspace | 184.7 ms | 12.0% | 209.2 ms | 4.7% |
| GLRT paired transform | 42.4 ms | 2.8% | 43.0 ms | 1.0% |

These stage measurements are inclusive. Parent and child rows overlap and cannot
be summed. The diagnostic pass ran after the uninstrumented pass and therefore had
warmer caches; its fractions locate work but are not exact steady-state proportions.
No cProfile timing was mixed into the uninstrumented CPU/wall result.

The most direct application optimization is a decision-only path for
`detect_first_glrt64`. Once a compatible non-overlapping pair is found after a
probe is fully evaluated, `first`, `decision_best_margin`, and the returned reason
cannot change. The earliest possible stop is after probe 2 instead of probe 10,
giving a workload ceiling near 11/3, or 3.67x. The returned prior hit's
`probe_index` does not reveal which later probe established confirmation; the
follow-up early-exit prototype measured a probe-2 stop at 2.5 Msps and a probe-5
stop at 5 Msps. A prototype must compare the complete serialized
`DwellDetection` on all inputs. Negative dwells still require all 11 probes, so
this does not provide a universal speedup. This optimization must remain separate
from `analyze_glrt64_dwell`, whose public full-analysis result requires every probe
and candidate response.

For full-response analysis, the measured target is the AVX2 coarse folded-anchor
grid. The tighter 220-ms/120-ms overlap accounting in `COARSE_GRID_AUDIT.md`
gives approximate whole-call ceilings of 1.25x at 2.5 Msps and 1.45x at 5 Msps,
even if the reusable coarse work is perfectly shared. Candidate-specific fine and
conditioned grids plus 220 GLRT scores remain. This bound makes clear that overlap
reuse alone cannot reach 10x.

Exact-execution candidates must preserve acquisition ordering, ties, all scores,
and the serialized application output exactly before performance comparison.
New approximate detector architectures remain in scope, but require separately
declared detection, false-positive, association and discovery-coverage gates.
The existing code already uses the native AVX2/FMA coarse backend, a padded
12-lane execution bank for 11 scientific CFO rows, FFT fine grids, factored
rotation caches, and the summed-autocorrelation GLRT path. Repeating those
optimizations under a new name offers no new gain.

Frozen evidence:

- `design.json`: `fa776c7c5eef4a00b25e380e8278faaea18e7ab547ac6bda5a8ec71bd83e1a11`
- `source_lock.json`: `296ba1382f3a6f076cb3024ddca266084564e93cfb4f1334f79b35c98227a38a`
- `run_profile.py`: `581bd9983c9636d3012ad8f8b74fa048896302d91d1b08c21bbaf612f31b25e6`
- `results.json`: `87abd4ed4e461693392b5782117579e3057796e1fb5dc1383aa2b75d3455680e`
