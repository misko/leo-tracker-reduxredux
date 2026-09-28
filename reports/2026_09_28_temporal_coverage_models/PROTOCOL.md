# Fixed models on broader temporal panels

Evaluate each complete timestamp-selected eight-record DS7/DS8/DS9 panel from
temporal_coverage_inputs, retaining all frozen eligible tracks. Never fit an
incomplete panel or substitute a recording. Dataset panels may execute once
their own eight input validations and seals are complete.

Three unchanged models: original independent Student-t4/100Hz, shared-track
multivariate Student-t4 with scale100Hz and diagonal matrix, and the same
multivariate model with10-second decay/20% nugget. All use original weak offset
penalty, full-catalogue normalization, visibility and training-only offsets.
One location and eight timing parameters per panel; no cross-dataset sharing.

Three prespecified source starts use E/N offsets (0,0),(3,-3),(-3,3)km relative
to the inherited geographic origin; all eight timings start at0. No prior
fit position or reference coordinate chooses a start. Bounds +/-12km and
timings +/-5s. L-BFGS-B maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30.
Select highest training likelihood among successful interior fits with raw
gradient infinity norm <=0.01. Preserve failures/unqualified runs; no retries.

Each worker capped180s/4GiB, BLAS1/nice19. One model worker while input workers
are active; at most two model workers after input preparation completes.
After selection, independently compare full-objective east/north gradients at
1m and0.5m (tolerance0.002), replay training score and compute exact held
mixture score with training-only offsets. Geographic scoring follows these
sealed stages and uses the same exposed unsurveyed operator reference.

Compare the earlier first-eight panels as historical equal-record-count
controls, explicitly retaining the differences in sample-rate mix, observation
counts and starting points. This is not an isolated causal time-span ablation.
The primary question is whether fixed existing models improve under broader
temporal coverage. No parameter/model selection by geographic error.
