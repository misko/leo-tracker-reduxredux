# Independent protocol review: new-day 300 m validation

The 116 disjoint scans support two scopes with different authority.  The
conditional replication scope deliberately refits a position for each new
16-scan replication group under the already frozen production algorithm and
that group's own blind-prior seeds. The strict predictive scope reserves the
deterministic sixteen-session subset in `holdout_protocol.json`: its five
locations are frozen before frequency scoring, so it permits no coordinate
fitting, basin ranking, loss tuning or candidate-prior tuning on new-day rows.

There are two useful but different analyses.

| Analysis | What is fixed or selected | What it supports |
|---|---|---|
| Production-shortlist replication | Every new disjoint 16-scan group refits under its frozen production algorithm, using that group's blind-prior seeds and legacy candidate/timing rules | A conditional replication of the deployed association pipeline. It does not test full-catalogue association or score the old five positions predictively. |
| Full-catalogue train/evaluation validation | Every causal catalogue member is searched using training rows only; candidate, timing, and CFO are frozen before evaluation rows are read | A genuine held-out frequency score for each fixed position, conditional on the causal TLE catalogue, receiver model, and chosen randomized split. |

The second analysis is needed for a position-accuracy claim.  The original
sixteen scans cannot supply it because their randomized evaluation rows already
participated in association/location discovery.  A disjoint new scan set can,
provided its candidate discovery never reads evaluation frequency values.

## Frozen full-catalogue protocol

1. Freeze the inventory, exclusion of the original sixteen session IDs, the
   deterministic sixteen indices `[0, 8, 15, 23, 31, 38, 46, 54, 61, 69, 77,
   84, 92, 100, 107, 115]`, five locations, causal snapshot rule, the exact
   existing saved randomized training mask, integer timing support `[-5, 5] s`,
   an elevation rule, a 250 Hz signal
   scale, a 30 kHz null scale, and a retention count `K` before frequency
   scoring. Save digests for the evidence sidecars, TLE payloads, locations and
   configuration.
2. For every new track, propagate every causal catalogue member in batches at
   the track observation times plus the eleven frozen timing offsets. At each
   of the five frozen receiver locations, profile only a per-track CFO on the
   training mask and calculate the training score. Visibility must be evaluated
   at that receiver and timing support.
3. Retain the deterministic top `K` candidate/timing hypotheses from the union
   of the five location-specific **training** rankings. The retention receipt
   must include the full candidate count, propagator failures, candidate/timing
   ranks, training score and a digest of the training mask. This remains a
   full-catalogue training discovery even though later evaluation only needs the
   retained states.
4. Seal the retained IDs, timing shifts and CFO values. Only then load the
   complementary evaluation frequencies and calculate residuals, capped
   duration-weighted RMS, null rate, candidate rank stability and predictive
   log score. Do not refit CFO, timing, identity or location on evaluation rows.
5. Compare the five frozen positions by their aggregate held-out score with no
   new position selection. Report the entire five-location table and an
   uncertainty procedure grouped by scan (and by candidate source where it
   recurs), rather than treating adjacent frequency samples as independent.

The full-catalogue denominator belongs in a mixture/evidence objective. A
top-`K` retained evaluation set must be labelled as *training-selected
full-catalogue retention*, not as a fresh `K`-catalogue search. Candidate/timing
selection is made once per track from training data; the corresponding CFO is
also fitted once from training data and replayed unchanged on evaluation.

## Feasible implementation path

`tools/research/run_blind_shared_orbit_coarse.py` already demonstrates the
needed pattern: catalogue batches (`64` candidates), receiver-grid batches,
training-only CFO profiling, causal TLEs, and explicit wall-time/RSS limits.
For validation the geography is much cheaper: use five fixed ECEF receivers
instead of a regional grid, and cache each batch's propagated ECEF states for
all eleven timing nodes while scoring all five locations. No global
reacquisition or spatial search is needed. `scanner_tle_screen.rank_curves`
shows the correct training-side profiling algebra, but it also calculates held
out diagnostics and therefore must not be called before the training retention
receipt is sealed.

The existing coarse runner's loader creates a chronological training prefix;
reuse its propagation and batch scoring mechanics only. The validation runner
must consume each sidecar's existing deterministic randomized mask unchanged:
it must not generate a new partition seed or a chronological split. Assert that
both partitions contain enough observations before any catalogue propagation.

Start with a declared 15-minute, 2 GiB pilot on a fixed small number of new
scans and record candidates/second, state-cache bytes and propagation failures.
Use that measurement to set a bounded batch/run count. A failed preflight is a
result; do not fall back silently to production-selected IDs.

## Claim boundary

A small held-out RMS at one frozen coordinate is frequency-model support, not
by itself a calibrated 300 m horizontal-accuracy interval. A 300 m claim needs
the frozen coordinate to outperform the other frozen alternatives under the
new-day held-out score, scan-group stability, and explicit sensitivity to TLE
age, timing/CFO bounds, candidate ambiguity, correlated samples and receiver
geometry. If full-catalogue training discovery cannot finish within the declared
budget, only the production-shortlist replication may be reported, with that
limitation in its title.

## Held-out worker review

`tools/research/day_frozen_position_holdout.py` uses the causal all-Starlink
candidate indices produced by `prepare_adaptive_tle_position_inputs`, rather
than the production winner shortlist. Its training selector indexes only the
saved training mask, and its synthetic evaluation-perturbation invariant test
is an appropriate guard for that boundary.

Before a strict run, its invocation must bind `--sessions` exactly to the
sixteen IDs in `holdout_protocol.json`; its current inventory-prefix default is
not the frozen evenly spaced subset. The receipt should record the partition
seed/authority and the post-propagation valid-candidate count plus failures,
not only the pre-propagation count and mask digest. Its retention receipt also
needs atomic no-overwrite creation before evaluation starts.

Finally, the implementation currently evaluates only the first training-ranked
hypothesis even when `top_k > 1`. A hard-MAP validation should set and label
`K=1`; a `K>1` run must evaluate a predeclared mixture over all retained
hypotheses. The frequency vector is present in memory during training because
the scanner sidecar is reconstructed as one track input, but the selector's
mask isolation plus its perturbation test support the narrower, correct claim:
evaluation values do not influence any training decision.
