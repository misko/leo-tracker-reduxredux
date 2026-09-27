# DS6 causal element freshness correction

The existing baseline selects the latest collected snapshot across providers.
At 23:01 UTC on September 26, a mirror download followed a primary download by
about two seconds, but contained older orbit elements. The first five DS6
scans therefore used older elements despite newer causal elements being
available. Download recency and orbit epoch are different quantities.

This research comparison takes the latest snapshot strictly before the
existing start-minus-505-second cutoff from each provider, then chooses the
newest epoch for each satellite. Ties use collection time and digest. It keeps
the baseline satellite roster and row order, uses no later snapshot, and never
loads ground truth in fitting. This is not a production deployment or a change
to the existing public archive-reader contract.

The all-43 audit found 8,847 changed catalogue rows for the first five scans and
zero changed rows for the other 38. In the five affected scans, 20/26/28/48/45
training-MAP track candidates changed elements. Removing a training-mean
constant offset still left frequency-shape changes reaching 6.21 kHz. This
quantifies catalogue sensitivity, not absolute orbit uncertainty or confirmed
satellite identity.

| Scan suffix | Baseline error, km | Fresh-element error, km | Held log-score gain |
|---|---:|---:|---:|
| 2e6b78f0cd0cbbbc | 9.053 | 1.998 | +60.41 |
| 3221795d82a1c7ec | 6.284 | 4.950 | +405.97 |
| 195bdbb87ad09b7f | 7.729 | 6.559 | +268.99 |
| 60d9d1e77c14da0a | 5.795 | 5.534 | +62.06 |
| cd6a029d633dcc0e | 9.461 | 6.597 | +949.27 |

All five affected scans improved both geographic error and held prediction;
none reached sub-kilometre error. Candidate proposals were rebuilt against all
objects in the baseline roster at the same five geographic anchors and timing
grid, rather than retaining stale-element shortlists. The likelihood, search
starts, bounds, holdout groups and optimizer settings match the sealed
baseline. All five winners converged inside bounds.

For the other 38 scans, complete element-record text identity permits exact
reuse of sealed baseline inference. Each reused output records that decision,
the baseline hash and element-source provenance. They are not labelled as new
fits. `summary.json` and `errors.csv` report complete membership and distinguish
refitted and reused scans.

The complete 43-scan result has mean horizontal error 3.317 km (previously
3.612 km), median 2.355 km (previously 2.425 km), maximum 8.482 km (previously
9.461 km), and 6/43 below 1 km. Two optimizer warnings belong to unchanged,
reused baseline fits; there are no search-boundary hits. All five validation
tests passed. The improvement does not complete the sub-kilometre objective.

Ground truth is read only in `summarize.py`, which hashes completed outputs and
the independent roof-coordinate authority. Tests cover per-object epoch
selection, deterministic ties, strict causal cutoffs, all-43 provenance and
exact baseline reuse. Candidate selection remains approximate, and the
location search remains local; this is not blind global localization.
