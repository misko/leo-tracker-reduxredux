# Historical orbit-state age uncertainty screen

Use the existing historical_orbit_forecast triplets and unchanged time/object
split. This is a separate uncertainty hypothesis, not a retry of the failed
mean correction or the older residual-derived age scale. Do not read radio,
station coordinates or DS11 errors. Predict the uncorrected three-dimensional
later-minus-current position vector using a normalized zero-mean multivariate
Student-t with four degrees of freedom and isotropic scale in kilometres.

Compare fitted constant log-scale a with age-dependent log-scale
a+b*log(1+age_days), b>=0. Bounds a[-6,8], b[0,4] protect numerical execution;
they are not physical orbit bounds. Source-balance training by assigning each
NORAD total weight one. Fit age starts b=0 and1, constant start a=0, with analytic
gradients. Select maximum training likelihood before validation. Require finite
successful fits, projected gradient<1e-5 and finite-difference discrepancy<1e-5.
Boundary b=0 is valid but offers no improvement; upper-bound solutions do not
qualify. Seal calibration before reading validation vector values.

Report all validation cases and mean log-score gain per distinct NORAD. Passing
requires positive mean and median source gain and strictly more than55% source
wins against the fitted constant model. This exploratory validation panel was
already exposed by the mean-forecast study; a pass would require independent
confirmation before a DS11 test. No mean correction, geographical fitting,
independent-error interpretation, or conversion of kilometre scale to independent
Doppler noise is authorized by this screen. Later orbital elements are reference
proxies, not orbit truth. Preserve failures and keep the original failed gates.
