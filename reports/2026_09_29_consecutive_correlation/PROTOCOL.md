# Fixed temporal-correlation ablation on consecutive panels

Reuse exactly the 18 four/eight-scan panels, inputs, eligibility, bounds,
optimizer settings and three generic starts from 2026_09_29_consecutive_panels.
The sole scientific change is decay_s from 0 to 10, using the existing
Student-t4 scale matrix 100² * (0.8 exp(-abs(dt)/10) + 0.2 I). This fixed
variant was already tested on other panels; do not tune hyperparameters on
the present outcomes. No geography-based choice between models is permitted.

Bind and verify the complete previous evidence inventory before preparation.
Reuse its frozen membership without resampling, dropping or replacing records.
Keep the original runner and launcher byte-identical. Select highest training
likelihood among successful interior fits with gradient infinity norm <=0.01.
Retain all three starts and all failures. No warm starts, fallback or retries.

Evaluate each selected fit with exact input/count checks, replay within 1e-7,
four E/N gradient checks within 0.002, and independent distance arithmetic.
Compare geographic error and full-mixture held prediction against the paired
zero-decay panel on identical tracks/held observations. Also retain the nested
four/eight held comparison, medians across three joint panels, and sub-km counts
out of three per size/dataset. These are not single-scan medians.

One scientific worker, no overlap with input/model workers; BLAS1/nice19,
12 GiB address-space cap, 300 s/process, MemAvailable >=14 GiB before each
launch. No RF collection, waveform reads, propagation, provider fetch,
component or golden-fixture changes. Exposed unsurveyed reference only;
no surveyed resolution, calibrated confidence or blind/new-site claim.
