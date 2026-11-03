# Fixed-model evaluation on 64 independent recordings

The user explicitly requested this 64-scan evaluation after reviewing the first
prototype's scientific stop. This authorizes evaluation of the remaining scans
despite individual failures; it does not promote failed posteriors or authorize
parameter tuning. The earlier experiment and its artifacts remain unchanged.

Select 64 recordings total: 22 DS9, 21 DS10, 21 DS11. Within each complete dataset
authority, sort by capture start and session ID and select zero-based chronological
indices floor(i*(N-1)/(n-1)), i=0..n-1. Freeze all session IDs and manifest hashes
before any fit; bind each scan's observations before its fit. Do not select using reference error or RF
fit quality, and do not replace unavailable/failed scans. This panel is distinct
from the earlier 48-scan selection and includes historically explored recordings.

Before any fits, the user replaced the proposed near-site initialization with the
standard adaptive pipeline's Sacramento prior. Saved current pipeline outputs for
the first DS9/DS10/DS11 scans all declare Sacramento center (38.5816,-121.4944),
radius 250 km; Reno is a separate 500 km region at (39.5296,-119.8138). The requested
evaluation uses Sacramento only. See pipeline-prior-audit.json and prior-audit.json.

The intended spatial prior is uniform over the Sacramento disk. The Gaussian-sum
representation approximates it with 32 equal-area annular-sector cells: four rings
with boundaries R*sqrt(i/4), eight equal angular sectors, each with weight 1/32 and
its exact uniform-cell EN mean/covariance. Overall mean and covariance match the
uniform disk. A finite Gaussian mixture is NOT an exact bounded uniform density;
report measured boundary leakage and label the approximation in every receipt.
Deterministic quadrature finds 2.54639% represented mass outside the intended disk;
the operational five-sigma orbit support radius is 489 km. These are distinct from
the 250 km intended prior and are not inferred from radio data or reference error.
There is no fitted/winner-based seeding or reference-directed prior location.

Height SD remains 0.1 km, UTC SD 1 s, each RX raw drift SD 0.5 Hz/s, and each
satellite epoch error SD 0.5 s. Nuisance means and histories reset for every scan.
The pure analyzer and RF physics are unchanged from the tested prototype. No state
transfers between scans, and all arms use the same retained observation sequence.

Arms: Gaussian sum (32 components, 1e-12 weight floor), greedy (one retained
child), and prior-only. The maximum candidate-child work is 65536 per factor.
The mixture cap matches the 32 initial cells: a 16-component cap would discard
half the initial mass even under an entirely uninformative background factor.
This choice is frozen before any RF fit and is not selected by reference error.
Candidate geometry covers every initial component's five-sigma horizontal support
(which exceeds the intended 250 km disk because of Gaussian tails) and +/-1 km height, using the causal
archived full TLE catalogue and reporting propagation gaps. Signals use the
verified 11.2 GHz canonical Doppler, actual-RF drift scaling, at most eight
time-spread original samples, and per-RX constant-CFO Helmert contrasts.
Noise and background priors, visibility handling, interpolation support, and
source-overlap exclusion are unchanged. An updated component whose center leaves
the intended 250 km region fails a support gate. This center check does not remove
Gaussian-tail leakage or turn the approximate density into an exact uniform prior.
No antenna roll/FOV or other model is fit.

The existing per-scan gates remain active. Stop a Gaussian-sum arm if an update
discards >1% posterior mass; stop any arm on support, numerical, or work-budget
failure. Record its status as abstention/failure, preserve available progress,
and continue to the next authorized arm/scan. Do not reinterpret a partial or
truncated posterior as a completed location. No broad-prior sweep in this panel.

Budgets: one numerical thread and 6 GiB virtual memory per fit; 90 seconds per
arm including load; 180 seconds per orbit export; at most two fit processes and
one sequential export reader. Run batches of at most eight scans and 15 minutes.
Review each batch's statuses before launching the next. No RF or raw-IQ collection,
no replacement scans, no automatic budget expansion, no scientific retuning.
Full-precision orbit and nuisance-state NPZ artifacts live in the owned bulk
directory /srv/bulk/leo/research/gaussian_sum_64_scan because the workspace has a
quota. Receipts bind their exact absolute paths and hashes; small manifests,
predictions, seals, code, and figures remain in the repository report directory.

Seal predictions before evaluator-only reference access. Use the same audited
operator roof coordinate as the prototype, with explicit unsurveyed-reference
limitations. Report by dataset and overall: all 64 attempts per arm, completion
and failure reasons, conditional completed-scan median/p90/worst point error,
sub-km success fraction over ALL planned attempts, and paired comparisons with
the unchanged configured center / prior mixture mean. Also report the originally
declared highest-weight-component prior-only point estimate separately, since
its arbitrary equal-weight tie makes it a weaker baseline than the center.
Point estimates must never be selected for closeness to the reference.

Report failure-inclusive empirical error CDFs, paired per-scan error plots,
retained-mass/consumed-support and runtime summaries, and density examples from
the first chronological selected scan of each dataset (not the best outcomes).
Label unsupported/partial outputs diagnostic. Do not pool conditional predictive
scores across unequal observation support. Reference containment is descriptive;
this repeated single-site panel is neither independent-site validation nor
satellite-identity truth. Independent means reset fits on distinct recordings,
not statistical independence of radio/environment errors.
