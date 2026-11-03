# Supplementary matched timing-start audit

After the frozen primary fits, compare original-window training optima to the
previous cached q020 fits. DS8 early and middle cold starts have training scores
116.430 and357.892 lower than previously found optima. This demonstrates local
optimization sensitivity without using geographic error for selection. All
primary artifacts and results remain unchanged.

For ALL18 sets, add three deterministic starts at E=-2,0,2km,N=0. At each
position, evaluate each scan's TRAINING q020 score over the existing41 timing
bank nodes [-5,+5]s in0.25s steps; choose the maximum per scan, then jointly
optimize E/N and all eight scan times. Candidate mixtures remain intact.
Select the highest training score among the original three qualified cold
starts and the three qualified grid-initialized starts. Never seed from the
reference location, held values, or another set's optimum.

Use the same optimizer/audit gates,90-second cap per set and three workers.
Verify the batched timing-grid scores against the scalar source model at the
selected grid node before fitting. Preserve all initial grid scores, chosen
times, and optimizer endpoints. This six-start result is supplementary and
must be reported separately from the frozen three-start primary comparison.
