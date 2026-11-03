# Four-visit frequency trajectory and frame sensitivity

Use all 18 tracks from the frozen training-waveform selection, without ranking
on prior outcomes. Select the first four original training observations greedily
spaced at least one second apart. Select up to two earliest original held visits
after the fourth training visit. Preserve short held coverage rather than replace
tracks. No waveform values select visits. The metadata support audit found two
tracks with only one eligible held visit; retain both, weighting tracks equally.

Reuse exactly bound excerpts from waveform_trajectory where available; read the
rest through public read-only ports. At most four 120-second checkpointed
extraction invocations. Numerical cap180 seconds, one thread/process. No new RF.

Use the same first eight frames, cached epoch/CFO and deterministic upconversion
correction. Fit residual frequency from symbols22–221 with ±1500Hz bounds and
the prior 25Hz grid/refinement. At each training visit also refit leaving out
each of the eight frames. Jackknife sigma is sqrt(7/8*sum((f_i-mean(f_i))^2)).
This measures sensitivity to frame removal, not calibrated absolute uncertainty.

Fit four straight-line trajectories on the same four visits: cached OLS,
refined OLS, cached weighted LS, refined weighted LS. The two weighted arms use
the SAME weights 1/max(sigma,25Hz)^2; 25Hz is a frozen stabilizing floor, not an
empirically calibrated noise level. No clipping, quality exclusions or tuning.
Fit actual tuned RF + cached CFO (+ residual for refined arms), subtracting the
first tuned RF for conditioning. Weights and trajectory fits use training only.

At each held visit score predicted frequency on symbols222–301 after matching
per-frame/carrier gain calibration on22–221. Average frames, then held visits,
then tracks equally. Include a local cached-held control. Report all failures,
search-boundary fits, weight floors, frame sensitivities, and forecast horizons.
Primary comparison refined OLS versus cached OLS. Secondary weighted controls
separate refinement from reweighting. No geographic or Doppler-truth claims.
Previous panel exposure and full-recording track construction remain caveats.
