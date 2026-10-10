# Lower update dispersion, persistent terminal displacement

The fixed conditional stationary replay reduces fitted-c mean update error from the standalone recovery candidate's 1.2548 km to 0.4882 km for cumulative mean and 0.4206 km for cumulative coordinate median. This is an additional multi-scan estimator over consumed data, not a deployed B7 or standalone accuracy gain.

|Fitted-c fusion|Regressed updates /193|Largest regression km|Terminal estimate error km|
|---|---:|---:|---:|
|One hypothetical episode: mean|49|0.486407|0.503346|
|One hypothetical episode: coordinate median|40|0.467874|0.476267|
|Dataset cold starts: coordinate median|35|0.484793|0.602872|

Regression comparison uses 1e-9 km numerical equality tolerance, not an inference gate. Full matched-arm comparisons are in [paired-comparison.json](paired-comparison.json). The lower update mean does not remove persistent displacement: the final fitted median remains 0.476 km from reference. The method can also worsen individual updates relative to a good standalone fix. None of these errors selected the frozen policy or a preferred deployed method.

All 193 members are included (63/51/34/45), both arms have zero outages, and standalone geographic errors exactly reproduce the sealed107 report. Hardware metadata does not independently establish stationarity; capture-order causality does not establish online availability. No covariance, motion performance, new frequency fit or achievement of the standalone 0.4 km goal is claimed. Keep this a conditional diagnostic pending independent operating-mode evidence and validation.
