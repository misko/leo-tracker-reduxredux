# Cheap one-peak CFO refinement: preparation

No native outcome trials until parent publishes this source-hashed protocol.
No production/native source or persisted contracts change. No recordings,
orbit predictions, positioning fits or RF collection.

This is **not a new discovery of continuous GLRT refinement**. The existing
[prototype](../../src/leo/analysis/starlink/glrt_refinement_prototype.py#L35)
searches the strongest three distinct maxima with exact autocorrelation DTFT
golden-section refinement, up to40 iterations per maximum. The
[September11 study](../2026_09_11_glrt_refinement_prototype/README.md) reduced
within-alias frequency-shift RMS46.09→8.65Hz at2.5MS/s and65.94→23.27Hz at5MS/s,
but acquisition/rank/alias errors remained and joint timing/CFO refinement
worsened one scan. Higher exact score did not guarantee correct frequency.
The novelty here is a much smaller one-peak computation and a matched test
on the partial/off-grid-support counterexamples from122.

## Available native information and two estimators

[Native GLRT](../../src/leo/analysis/native_presence/presence.c#L711) has all512
real power ordinates after its final FFT and returns only the best bin. Its
immediate circular neighbors are available internally at zero additional FFT
cost. They are discarded by the public three-scalar diagnostic output. The
63 positive-lag autocorrelation coefficients exist in the packed FFT input
before that FFT; they can support exact power derivatives if retained. These
are summed per-frame correlation powers, not a single coherent frame phase.
Native spectrum storage is reused for control after exact processing.

1. **Three-bin log parabola:** fit log power at best−1,best,best+1, require
   positive values and negative curvature, clip offset to±.5bin. Otherwise
   retain original bin. This prototype also accepts only if exact polynomial
   power at the proposal is at least original power. Thus its actual proposed
   cost includes one63-term verification, not merely three logarithms.
2. **Bounded three-step Newton:** from the same original best bin, evaluate
   exact polynomial power/first/second derivative, require negative curvature,
   project every proposal into originalbin±.5, and accept only nondecreasing
   exact power. Stop after at most3steps or first failed condition; no ridge,
   alternative-peak search, reconditioning or changed epoch. At most6
   63-term polynomial evaluations, with derivatives and power sharing phase
   factors. Physical symbol alias wrapping applies at return only.

Flat/nonpositive/invalid-curvature cases retain baseline; no confidence claim
is inferred from curvature. A wrong coarse peak remains wrong. The±.5bin
trust interval cannot rescue arbitrary multi-bin mistakes. Both variants
preserve original native exact/control scores, margin gate and membership;
only reported conditional CFO changes. A frequency-only diagnostic gain is
not a detector or positioning promotion criterion.

## Frozen matched design

Replay exactly the480 generated inputs from122: phases[-.4,-.2,0,.2,.4]Delta,
amplitudes[.25,1], cutoffs[.00015,.001,.020]s, seeds122000..122015. These inputs
are consumed development, not new validation. No new phases/seeds are added;
first establish whether the cheap approximation helps at all. Each input
gets exactly one unchanged native call plus both mathematical refinements
from the same correlations. Keep all failures/rejections, all phases and both
amplitudes; preserve baseline margin>=.025 admission, with no .175 floor.

The research adapter reconstructs the exact64-symbol correlations through the
existing Python research helper. Before accepting any row it checks native
exact/control/CFO against122 to absolute1e-10, and reconstructed coarse score
against native1e-10 and coarse CFO1e-8Hz. It does not expose a new native ABI.
Python reconstruction/refinement runtime is recorded separately from native
call time and must not be advertised as the incremental embedded cost. A
later native implementation would require its own differential tests/build.

Report all-cell and admitted-only paired signed bias/RMS/p95/worst frequency
error, regressions, fallback reasons, native-parity failures and runtime.
Compare against the injected synthetic frequency only; no known receiver or
satellite reference enters. Keep alias-folded and raw seam errors distinct if
new seam trials are ever separately authorized. Current input phases do not
test acquisition aliases or half-bin ties. Six pure correlation tests cover
both signs, the circular seam, flat/no-op behavior, analytic derivatives and
amplitude invariance without native outcome calls. The exclusive claim prevents
automatic retry after an incomplete run. No universal125Hz floor or improvement
to DS16/17/18 position error is assumed.
