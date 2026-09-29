# Next proposal: measure spatial information after timing adjustment

The tested receiver corrections and identity-coupling models have not supplied
reliable short-set sub-km gains. Before another geographic model grid, quantify
whether the existing likelihood distinguishes kilometre-scale position changes
after adjusting each scan's timing. This is an information diagnostic, not a
proposal to use the exposed reference as a prior or fit target.

First review the earlier slope-identifiability and timing studies to avoid
duplicating their completed work. Then define a bounded test on the current
consecutive-panel q020 model: local position curvature with scan timing profiled,
plus finite displacement checks where local curvature may be misleading.
Use training-selected coordinates as centers. Freeze displacement directions,
distances, timing starts, bounds and numerical tolerances before execution.
Keep candidate/visibility switches and failed profile optimizations explicit.

Do not interpret inverse curvature as calibrated geographic confidence: the
noise model, candidate uncertainty, reused data, unsurveyed reference and shared
errors can make it overconfident. Compare profile score changes with held
prediction separately. A narrow but biased profile suggests model/systematic
error; a broad profile suggests inadequate spatial information. Those outcomes
call for different next models and should not be conflated.

No profile diagnostic has been implemented or executed in this report. Further
work should use existing DS7/DS8/DS9 observations and bounded jobs, without new RF.
