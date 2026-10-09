# Fixed frequency width: 125 Hz versus 100 Hz

Preparation only until a reviewed protocol is frozen and published. This is a
research model comparison, not a production change or a physical noise estimate.
The [proposal](PREPARATION.md) motivates the test and its consumed-data limits.

This execution narrows the proposal's optional grouping step: it reports the
full consumed census and each dataset, without randomized groups, independence
claims or group-based uncertainty estimates. No parameters are trained. Proposal
decision gates are frozen explicitly: candidate versus matched control must
improve pooled mean and median by at least 5%, with dataset means worsening no
more than 5% and pooled p95/worst no more than 10%. Relative to each archived B7
endpoint, the count regressing by over 1 km must not increase versus control.
Archive-to-control and archive-to-candidate deltas are reported separately.
Failure retains 125 Hz without choosing another width from these same results.

All 63 DS16, 51 DS17 and 34 DS18 members are retained. The immutable iteration85
B7 endpoints define the baseline, using iteration87's verified production model
reconstruction. The control must exactly reproduce both archived objectives
within 1e-6 and nest the original physical/clock gradients bit-for-bit.

The sole candidate change is `score.sigma_hz=100` instead of 125. A shallow model
copy replaces its immutable score; every design matrix, bank, clock center and
prior precision is shared unchanged. The current production model reads score
directly on each evaluation, has no likelihood cache and retains no base-model
alias. Tests cover this contract. All Gaussian/clutter normalization remains.

Each member receives four fits: two widths times fitted-c and c=0, each 90 seconds
and 600 iterations. All start at the identical archived fitted-B7 vector/clock;
the c=0 fitter locks static c and both RF-time terms. This is a conditional c
ablation. Local position radius remains 25 km, timing sigma 2 s, receiver slope
bound ±60 Hz/s and satellite slope sigma 0.5 Hz/s. No new regions or retries.

Returned objectives and the physical plus clock KKT audit are recomputed. The
unchanged 0.001 threshold, physical constraints and clock bounds determine
qualification independently of optimizer success. Unqualified/failed candidates
fall back to the same-arm qualified 125 Hz control, then the archived B7 arm.
Control failures fall back to the archive. Scores from different widths never
select operational winners. Raw failures and fallback origins remain visible.

The inference engine reads no reference fields and computes no position error.
Later reporting will join evaluation-only references after choices are sealed.
Receipts retain score components, selected residuals, responsibilities, clutter,
assignments, clock norms, convergence, runtime and full fitted parameters for
separate frequency/association versus position comparisons. RMS over maximum
assignments includes clutter rows and is explicitly labelled; it is not a
calibrated measurement-noise estimate.

`engine.py --label LABEL` executes one member; `--shard 0|1` is also available.
Attempts and terminal results are append-only and protocol-bound. The parent
controller owns immutable process claims and bounded label batches. Execution
requires OMP, OpenBLAS and MKL thread counts of one and at most two concurrent
workers. Input failures remain terminal rows; no member is silently omitted.

`freeze.py` verifies inherited source hashes, binds all 148 input authorities and
interleaves dataset labels deterministically. It writes a new protocol but
performs no objective calculation or fit. No reserve or new RF access is needed.
