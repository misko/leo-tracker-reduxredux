# Remaining budget for a whole-call 10x result

This review uses the frozen server receipts. It is cost accounting and an
architecture proposal, not ARM evidence or a new detector result. It does not
change routing, thresholds, discovery cadence, or previously reported outcomes.

## What the observed cache can and cannot deliver

The V6 replay spends 665.672 ms in the blind reference and 370.537 ms in the
candidate over 256 receiver-visits, for 1.797x. Its routes are 95 cold, 35
expired, 52 failed predictions, and 74 accepted hits. The 182 blind routes are
71.1% of all receiver-visits.

| V6 accounting | CPU |
|---|---:|
| 10x whole-call budget | 66.567 ms |
| Accepted-hit cost | 21.318 ms |
| All nonhit cost | 349.218 ms |
| Current mean per nonhit | 1.919 ms |
| Permitted mean per nonhit if accepted-hit cost remains | 0.249 ms |
| Required reduction of nonhit cost | 7.72x |

Making every accepted hit free while leaving the measured nonhit paths intact
would improve the whole replay only to 1.906x. Cold plus expiry alone cost
232.750 ms over 130 calls; even if hits and all failed-prediction work were free,
that fixed observed cost caps speedup at 2.860x. These calls cannot be removed by
better positive tracking because repeated cold visits include keys that have not
established positive state, and expiry is an explicit evidence policy.

The partial-two-frame cache illustrates the same limit. Its hit-only speedup is
29.5x, but 187 blind calls leave a 1.336x whole-call result. Even free accepted
hits cap it at 1.352x; its nonhit path still needs an 8.15x reduction to fit the
10x budget.

The receipt does not separate every failed fast check from its subsequent blind
call. A rate-matched proxy charges each of the 126 attempts the observed mean
accepted-hit cost at that rate, then estimates acquisition from cold and expiry
calls. That model leaves 29.981 ms for 182 acquisitions, or 0.165 ms each,
versus a current 1.824 ms acquisition proxy: an 11.07x reduction. This is a
planning model rather than a measured stage decomposition. The less restrictive
0.249 ms bound above is necessary but not sufficient because it gives failed
checks no separate cost.

The independently qualified FP32 FFTW blind detector costs 490.922 ms over the
same 256 new-development receiver-visits, or 1.918 ms per call. A uniform
full-coverage detector has 0.260 ms per receiver-visit under the V6 10x target,
so the qualified FP32 detector remains 7.37x over budget. Its native profile
spends 36.6% in rank and 61.5% in confirmation. Optimizing only one stage cannot
meet the remaining factor. The earlier FP32 transform change delivered 1.62x;
rank-seeded acquisition delivered 1.94x while losing 28/36 old development
positives; and coefficient-transposed final GLRT was 1.047x slower. None is a
path to the required budget by incremental composition.

## One next architecture: a visit-wide ambiguity engine

The next bounded experiment should replace the rank-then-confirm acquisition
pipeline with one visit-wide pilot ambiguity engine. It should run on every
receiver-visit, including cold and quiet keys, so it measures evidence rather
than skipping discoveries. Cache routing can remain outside the experiment; a
uniform engine avoids paying a failed fast check before acquisition.

The engine would make one strided pass over the 120 ms CI16 receiver input,
forming energy prefix sums and pilot-phase sufficient statistics. A batched
frequency-domain correlation would produce timing-by-CFO ambiguity values for
all six windows and both exact and rolled-control pilots while reusing input
spectra, template spectra and twiddles. A fixed number of peaks, declared from
the geometry before data evaluation, would receive fractional refinement from
the retained sufficient statistics. The final exact/control margin and physical
CFO would come from that same computation, rather than rereading the selected
window through a separate coarse, fine and fractional confirmation pipeline.

This is a new detector architecture, not an assertion that the existing GLRT is
algebraically reproduced. Its first server gate must include the complete C call
from natural strided CI16 ingress through candidate output and target no more
than 0.260 ms per receiver-visit, preferably 0.20 ms to leave host-call and state
headroom. A both-RX physical visit therefore has about 0.520 ms total at the
hard budget before wrapper and queue costs. A rank-only or FFT-only benchmark
does not satisfy this gate.

Scientific qualification must freeze grid, peak count, normalization and
thresholds before replay; compare all 256 new-development receiver-visits and
the fixed pilot/noise/tone controls; and report reference-positive retention,
extras, timing/CFO association, margins, no-candidate cases and total cost.
The existing one-confirmation reference establishes top-candidate behavior, not
complete multisignal sensitivity. The separate all-six-window diagnostic found
additional positive trajectories, so any multisignal claim needs a separately
costed all-window reference and must not inherit the one-confirmation speed
comparison.

No current artifact demonstrates that this engine can reach 0.260 ms, and no
server result would establish ARM performance. The budget does show why the
next experiment must change full acquisition and evidence computation across
both dominant stages. More cache policy work alone cannot close the measured
gap while retaining cold, expiry and failed-check coverage.

Calculations are reproduced by `review/ten_x_budget.py` and recorded in
`review/ten_x_budget.json`. The script SHA-256 is
`b07c2f75f8e146926e2f2aa8f7bd6dc9f9ef9d1010ac4f467db210d7c8475256`;
the generated JSON SHA-256 is
`3abc1806175982525adb7c85c088fc1aa29aa343fb088462cc101932d768c83c`.
