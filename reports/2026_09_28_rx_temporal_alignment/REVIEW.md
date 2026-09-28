# Independent review: temporal alignment diagnostic

## Scientific scope

This diagnostic is descriptive. It compares each saved visible nominee forecast with the nearest
observed candidate in the same alias circle and joins frozen within-family D/T scores and presence
probabilities. A 500 Hz or 1500 Hz nearest-candidate fraction is neither a calibrated identity
probability nor chance-corrected evidence: saved candidate duplicates remain in counts, candidate
density changes the opportunity for a near match, and no verified absence labels exist.

The normalized retained-track prior must be computed after excluding the saved `other` component.
Invisible nominees and receivers with no candidates contribute zero, without redistributing prior
mass. Both receivers' `canonical_rx0_hz` values are already bias-corrected into the common canonical
coordinate in the frozen dataset, so a shared forecast coordinate is appropriate. Track IDs alone
are not identities; component alignment must use `(track_id, catalog_number)`.

Elapsed time must start at each lane's first reception forecast, because different lanes in one
recording need not share a start. The fixed bins are `[0,30)`, `[30,60)`, `[60,90)`, `[90,120)`,
`[120,180)`, and `[180,infinity)` seconds. Each group must average windows within recording before
averaging recordings, expose both denominators, and retain empty-bin groups explicitly. Each role
also needs an `all`-time summary so its complete window population remains visible alongside bins.

## Source gates

Before execution, require:

1. Exactly six unique temporal-transfer folds matching the calibration recordings, with no window
   outside the two declared roles and a one-to-one D/T/dataset window join.
2. A finite positive alias period; finite prediction, observed-frequency, probability and score
   values; and valid timestamps.
3. Exactly one terminal `other` component, track-candidate components before it, and unique
   `(track_id, catalog_number)` keys aligned in order with every forecast row.
4. Per-lane reception origins, valid fixed-bin membership, `role:all` aggregates, and tests with
   multiple lanes whose reception starts differ.
5. Equal-record aggregation tests with unequal window counts, plus periodic-boundary, invisible,
   empty-receiver, duplicate/missing-join and input-immutability tests. Inspect the CLI input-hash
   binding independently.

The launcher verifies the preceding evidence index and freezes the dataset, transfer result,
diagnostic source, tests, protocol and launcher. Its 120-second, 4 GiB command is bounded and uses
single-thread numerical-library settings. The fresh output path must remain mandatory.

No outcome was available during this source review. Any later decline can describe association
with role or elapsed time under the frozen construction, but cannot distinguish forecast age from
detector behavior, changing candidate density, intermittent or absent signal, handoffs, nomination
failure, or other role-correlated changes. It cannot establish direction or satellite identity.

## Final source gate

The finalized implementation uses the complete serialized lane identity for each reception
origin, exports whole-role and fixed-bin summaries, rejects unknown roles, verifies a positive
finite period, checks D/T window populations and metadata, and validates candidate frequencies,
forecast frequencies, presence probabilities, scores, and nominee key alignment. The production
CLI additionally requires six folds. The frozen dataset itself has 12 calibration lanes in six
recordings, exactly one terminal `other` component per lane with only track candidates before it,
positive finite periods, and only the two declared roles.

The multi-lane-origin and unequal-window-count tests directly cover the two aggregation risks.
The installed-environment six-test run and Ruff check passed according to the frozen launch review.
The repository development environment lacks SciPy and therefore cannot collect this test module;
that is an environment dependency difference rather than a source failure, because execution and
the reported passing tests use the installed API environment. With the preceding evidence hashes
restored exactly and preserved by the launcher, I find no remaining launch blocker.

## Outcome audit

The bounded run exited successfully and exported 2,719 unique windows: 1,356 reception and 1,363
held-frequency windows from all six recordings. The independent audit reconstructs every dataset
to transfer-result join, retained-prior normalization, periodic nearest distance, per-lane elapsed
bin, per-record mean and equal-record aggregate without importing the diagnostic implementation.
It passes and binds results digest
`7ab58c5a8fe5b59053ec9e8f3539b7c28226521693d6ddb7bf1ffdfcf27ed08b`.

At 500 Hz, equal-record aligned prior mass falls from `0.348218` to `0.001893` on
RX0 and from `0.293692` to `0.030381` on RX1. The decline occurs separately in all six
recordings on both receivers. Forecast-visible prior mass remains `1.0`, while mean candidate
counts fall from `2.221` to `1.275` on RX0 and from `1.478` to `0.972` on RX1. The unchanged
visibility shows that the saved forecasts continue to assert geometric visibility; it does not
show that the nominated transmitters remain present.

Mean frozen posterior presence changes from `0.542` to `0.0359` for D and from `0.544` to
`0.1848` for T. T's larger later presence is not tracking confidence: the temporal-transfer score
already shows T loses to the empirical reference in four of six later recordings. The sparse
30--60 second held-frequency bin contains only eight windows from four recordings, and there is no
support at or beyond 120 seconds, so those bins cannot support a smooth horizon trend.

These results establish a large descriptive loss of candidate-frequency alignment across the
observed role boundary under the frozen nominations. They do not identify forecast age, handoff,
detector behavior, signal absence, or forecast error as its cause, and they do not establish a
satellite identity. The proposed frozen signed-residual and continuity diagnostic is the right
next measurement: it can separate a continuous offset or slope from disappearance/replacement,
provided it reports receiver and nominee trajectories without choosing a best nominee from future
outcomes.
