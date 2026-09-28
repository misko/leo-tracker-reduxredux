# Fixed models on the union of existing panels

Before new fits, freeze the session-ID union of historical first-eight and
timestamp-selected broad-eight panels for each of DS7/DS8/DS9. Require exactly
15 recordings per dataset (one overlap), chronological ordering and matching
artifact hashes for overlaps. Prefer the broad archive for duplicate sessions.
Keep every eligible track. The union has denser early coverage; it is not a
uniform-in-time sample or an isolated time-span ablation.

Use both unchanged multivariate Student-t4 scale100Hz models: shared track
scale with diagonal matrix, and temporal correlation with10s decay/20% nugget.
Retain offset prior, visibility, full catalogue normalization and visit split.

Fit the three separate15-record panels, all45 together, and each30-record pool
excluding one dataset. Pool starts use only included datasets' previously
qualified broad-panel positions. Initialize each record timing from its
same-model prior separate fit (broad-panel timing for overlap, historical for
historical-only). Separate15-record fits use broad, historical and origin
position starts, with the same timing vector. No new result or geography selects
membership, initialization or model.

Select the highest training score among successful interior fits with raw
gradient infinity norm <=0.01. Position bounds +/-12km; timings +/-5s.
L-BFGS-B maxiter140, maxfun200, ftol1e-14, gtol1e-8, maxls30. No retries.
At each qualified donor fit, adapt excluded-dataset timing/offsets at fixed
donor geography with timing starts0,-2,+2. Select by target training score.

Replay all training/held scores. Check selected source position gradients at
1m/0.5m using the full objective (tolerance0.002). Compare pool/transfer held
scores with exact same-model separate15-record fits, reconciling track sets,
recording IDs and held counts. Preserve unqualified fits and all failures.
Geographic scoring follows sealed fits and held evaluations, against the same
exposed unsurveyed reference. Do not choose a model or panel by geographic error.

Each scientific process capped180s/4GiB, BLAS1, nice19; at most two workers.
No new RF, IQ reads, propagation, bank export or catalogue fetch.
