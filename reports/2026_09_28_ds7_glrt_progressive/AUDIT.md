# Progressive evaluator audit notes

`evaluate.py` accepts only one complete, source-sealed, two-repeat replay with
fresh `original` and `optimized` rows plus at least one additional method. It
requires every method/repeat to cover the identical frozen DS7 cohort and rate
mix. Science is calculated once from repeat zero; both repeats contribute to
the mean of per-visit median CPU and wall timing.

The evaluator imports the prior DS7 scorer only after verifying its SHA-256.
It separately reports exact fresh-original agreement with the sealed prior
original receipt, but uses the fresh original as this run's scoring reference.
It retains its reference-negative denominators, positive-hypothesis and
receiver/probe recovery, identity-linked confirmations, unmatched extras, and
matched deltas. Extra candidates remain reference-relative extras, never
physical false alarms. The 90% and 80% confirmation flags, with hypothesis
recovery as secondary context, are development gates only; they make no
generalization, oracle-truth, or deployment admission claim.

The source and timing checks deliberately reject incomplete receipts, failed
rows, missing repeats, duplicate visit rows, rows outside the frozen cohort,
invalid rate coverage, absent baseline methods, and negative/non-finite timing.
The evaluator never invokes DSP or reads IQ payloads.

Candidate recovery uses the scorer's one-to-one timing/CFO association within
the same visit, receiver, and probe; it does not require equal candidate rank.
Each method records its actual returned candidate-response counts, rather than
borrowing a configured candidate limit. Candidate confirmations on a
reference-unconfirmed receiver/visit are retained as reference-relative added
activity, never physical false alarms. The neutral `development_recovery_gates`
carry 90% and 80% matched-confirmation thresholds; positive-hypothesis recovery
is secondary context. They are emitted again for every native-rate stratum so
sparse high-rate evidence cannot be hidden by the 16-visit 2.5 MS/s stratum.

## Frozen sparse-method review

The evaluated `methods_sparse.py` hash is
`a89efd9009d435f81921844a1e1156388f1732e1d595a20eef2acbe29f1259df`.
`optimized_full` uses the same eleven-probe, two-receiver, eight-candidate
configuration and chronological decision fold as the benchmark detector; its
real saved-IQ parity control is a necessary check. Fixed sparse methods return
only actually executed probe responses. They do not fabricate skipped probes as
negative evidence.

`progressive4` first evaluates indices 0, 3, 6, and 9 for both receivers, then
adds unvisited indices in index order only for receivers without a fresh
standard confirmation. It reuses the initial responses, prevents duplicate
receiver/probe work, and folds all returned responses by their real
chronological probe indices. Receiver-specific early stopping deliberately
changes the evidence inventory, so confirmation recovery is not numerical or
downstream-equivalence evidence.

## Final composite receipt audit

`run-03` is complete: 560/560 calls, zero failed calls, and all 37 sealed
source hashes match at its terminal receipt. It is intentionally a composite
receipt. Its first 526 rows are byte-for-byte the interrupted `run-02` prefix
(`104fc2d0e47c2dd993d3d8a30a0f66d8e2e840bb71cc5260acfad9f1b8a7d240`),
whose predecessor receipt hash also matches. The resume executed only the
remaining 34 rotated calls and records a fresh process, fresh method objects,
and cold caches. The composite timing must therefore not be described as one
uninterrupted warm process; only the final 10 MS/s timing repeat spans restart.

Every method has all 28 visits in each repeat, and all serialized results are
exact across repeats. The fresh original is exact against the sealed prior
original on 28/28 repeat-zero visits. Reference science counts use repeat zero
only: 16/4/4/4 visits at 2.5/5/7.5/10 MS/s, 1,154 positive ranked hypotheses,
3,774 negative hypotheses, 437 positive receiver/probe pairs, and 42 confirmed
receiver/visit pairs. These are reference-relative identities, not counts of
independent physical emitters.

For both repeats, each returned probe from `windows6`, `windows4`, `windows3`,
and `progressive4` exactly equals the corresponding fresh-original serialized
probe: respectively 672, 448, 336, and 652 returned probes. There are no extra
probe keys or mismatches. Reduced-budget methods also produce scalar candidate
tuples that are subsets of the corresponding original inventory after ignoring
candidate rank: 4,928 (`candidates4`), 7,392 (`candidates6`), 1,344
(`windows6_candidates2`), and 896 (`windows4_candidates2`) tuples, with zero
unmatched scalar tuple or extra probe. This is stronger than the scorer's
2-microsecond/8-kHz association, but it applies only to retained evidence.

No method creates an added confirmed receiver/visit relative to the original;
the scorer likewise reports zero unmatched candidate positives. The generated
tables agree with these denominators and with the raw mean-of-per-visit-median
timing calculation. Their 90%/80% entries remain exposed-cohort development
gates. In particular, the 7.5 MS/s confirmation denominator is only two and
the other high-rate strata have four visits, so a passing high-rate cell is not
a generalization or deployment claim.
