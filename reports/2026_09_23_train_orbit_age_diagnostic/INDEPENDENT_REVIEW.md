# Independent review: TRAIN actual-element-age diagnostic

Reviewed `2026-09-23T22:14Z` after the sealed result was present. Scope was the
frozen protocol, the epoch-recovery and descriptive-analysis source, the saved
epoch export, `results.json`, `REPORT.md`, and their source bindings. I did not
open VAL, TEST, IQ, GLRT, tracks, position outcomes, reference coordinates, or
run a fit.

## Confirmed inputs and causality

`results.json` hash is
`85bb4b8151feea10db77a6b166dba8ac5183fa4705b214e54824b5e8aa219b04` and
binds protocol `1179108712c5f6ab98365aed8badae675e68ccd052d57df55a779cc9fcf06986`,
recovery helper `16831c28277a0c5342b05336ab4fc666312fa083cdc07f86b6c7a8bfb5366b6d`,
analyzer `c48e1da725c7942692681cd2439850fe4cf4f6b832df2f165f09d027b1995c83`,
the sealed paired inference
`12a5906d2c9611799065d1e7fcb736f21de0ff0bb7b7d6ebb1a55fb6fdec65d1`, and
the recovered-epoch export
`b0a07a826d99f0880df03e8687e530e074f754c323066c3199a9f8e403ad01c1`.

The recovery helper takes its candidate IDs exclusively from the already-fixed
Sacramento/5-second parent arms: the 72-session first TRAIN arm and the 79-session
second TRAIN arm. It checks the 6,988 fixed-track count against the paired
support, requires 151 unique strict-metadata session IDs, and uses the metadata
record's `(snapshot digest, collection UTC)` key to select an archive snapshot.
`TleArchiveReader.read()` is therefore called on the exact causal snapshot record,
and `parse_element_sets()` rejects duplicate NORAD numbers before the candidate
epoch is admitted. The saved export has 6,988 track rows, 2,989 distinct
`(session, candidate)` joins, 151 sessions, and 12 digest/time snapshot records.
All 486 paired rows have a recovered exact session/candidate join; no recovered
candidate has a negative collection-time-minus-element-epoch age.

The pair reference time is correctly reconstructed as collection time plus the
already sealed `snapshot_collection_age_s`. In the paired source that value is
the mean of the contemporaneously matched RX support-center UTC values minus the
same session's causal snapshot collection time. The age calculation therefore
uses the parsed candidate element epoch and pair support time, rather than
mistaking snapshot collection age for element age.

## Confirmed output and interpretation

The result has the reported 486 pairs, 407 session/candidate groups and 138
sessions. Its 0.207--3.150 day element-age range, median 0.862 day, four
quantile bins, and marginal and TRAIN/lane/look-demeaned correlations reproduce
from the saved fields. The 407 groups are the right observational grouping to
show alongside 486 receiver-pair rows; the report does not treat the rows as
independent causal experiments.

No age-based selection is present: the paired subset, matching gates and fixed
parent candidates predate the element-age lookup. The report labels the
correlations and quartile means as descriptive, preserves RF/group heterogeneity,
and explicitly rejects an age correction, causal conclusion, calibrated orbit
error, or truth claim. It correctly distinguishes catalogue-update variability
from truth-referenced orbital error.

`ruff check recover_epochs.py analyze.py test_analysis.py` and
`pytest -q test_analysis.py` passed in this review. The test proves stratum
demeaning; source and saved-output accounting above provide the additional join
review.

## Limit

Paired rows carry `snapshot_collection_age_s` but not the snapshot digest/time
directly. The sealed pairing source derives that age from the strict metadata's
same per-session causal snapshot, and recovery uses that metadata, so the saved
workflow is consistent. A future reusable contract could carry the snapshot key
on each paired row and assert it again in the age analyzer; that would strengthen
standalone stale-input detection. It does not change the current descriptive
result or justify any numerical rerun.

No actionable defect found for publication within the stated descriptive scope.
