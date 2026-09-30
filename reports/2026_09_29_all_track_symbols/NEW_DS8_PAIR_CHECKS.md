# Two previously unexamined DS8 visits fail the paired-receiver gate

Two additional 120 ms visit excerpts were recovered, but neither has a frame
passing the pilot gate on both receivers. These runs add single-receiver soft
observations, not corroborated header bits or decoded fields. The quality
threshold was not lowered to produce a positive result.

## Selection and duplicate check

Among the newly qualified candidate-labeled DS8 tracks, visits DS8-F027/19 and
DS8-F039/84 each passed five of seven evaluation frames in the 14-frame run.
The seven-of-seven visit DS8-F039/1498 was already identified as S13. The two
five-frame candidates had no matching `(session, visit)` in the prior signal
inventory, so both were selected, without choosing between them using header
outcomes. This establishes novelty relative to that inventory, not an exhaustive
claim that no other project artifact has ever touched their raw samples.

Their prior conditional geometric candidates are STARLINK-34271 and
STARLINK-30711, respectively. Candidate names do not imply decoded IDs and were
not used to fit the radio symbols.

The generalized `paired_ds8_recovery.py` takes explicit unit, visit, and source
receiver arguments. It retains the exact earlier source candidate rank, requires
the peer candidate to pass acquisition margin and lie within two samples of the
source frame epoch, then selects the largest peer acquisition margin. It verifies
manifest hashes, common valid-start counters, RF/edge/channel consistency, and
the source candidate CFO. Candidate alternatives are not searched using unknown
header bits. Input aliases and their inventory hash are recorded automatically.

## Results

Each receiver produces 89 complete frames from the existing 120 ms recording,
with 45 held evaluation frames. Pilot coherence must exceed 0.5.

| Visit | Receiver | Qualified / evaluation frames | Median coherence | Maximum coherence |
|---|---:|---:|---:|---:|
| DS8-F027 / 19 | 0 | 27 / 45 | 0.509 | 0.575 |
| DS8-F027 / 19 | 1 | 0 / 45 | 0.369 | 0.431 |
| DS8-F039 / 84 | 0 | 0 / 45 | 0.417 | 0.478 |
| DS8-F039 / 84 | 1 | 34 / 45 | 0.528 | 0.584 |

The common data-carrier counts are 27 and 28. There are zero jointly qualified
frames in either visit, so the paired word and header assays abstain. This is
not a measured zero header agreement or evidence of absent messages. Timing
compatibility and strong single-receiver recovery do not guarantee a usable
second receiver.

The peer's weaker signal, its candidate selection, and calibration remain
possible causes; this experiment does not distinguish them. The conclusions
apply to these excerpts and this frozen candidate-selection rule, not the full
tracks, every candidate, or all DS8 data. Further candidate/calibration tests
would need discovery/held separation rather than choosing a hypothesis because
its unknown bits resemble the other receiver.

## Artifacts and checks

Ignored outputs are in `local/paired-ds8-DS8-F027-v19/` and
`local/paired-ds8-DS8-F039-v84/`. Each includes both soft arrays, original
candidate parameters, raw excerpt hashes, calibration/evaluation frame splits,
per-frame pilot diagnostics, source selection hashes, and alias checks. Original
S13 and census results were preserved. Empty header results correctly report
zero qualified frames rather than inventing bit strings.

Both read-only runs completed within their five-minute process limits, without
new RF collection. All 35 relevant existing tests and Ruff checks pass. No
numerical data, remote branch, or deployed service was changed outside ignored
research outputs.

## Follow-up: calibration-selected peer candidates

`peer_candidate_audit.py` checks every distinct stored peer candidate that
passes acquisition margin and lies within two samples of the original selected
frame epoch. Candidate duplicates are collapsed using epoch and CFO rounded to
six decimal places. The original raw excerpt hashes are verified; original
paired outputs are preserved.

Select a candidate by its median pilot coherence on **calibration frames only**,
with rank as a deterministic tie-break. Then inspect its separate evaluation
frames and their intersection with the source receiver's qualified frames.
Neither the candidate choice nor the comparison uses unknown header bits.

| Visit / peer | Candidate rank | Calibration median | Evaluation median | Evaluation maximum | Evaluation passes |
|---|---:|---:|---:|---:|---:|
| F027/19 RX1 | 0 | 0.366 | 0.369 | 0.431 | 0 |
| F027/19 RX1 | 4 | 0.076 | 0.064 | 0.189 | 0 |
| F039/84 RX0 | 0 | 0.414 | 0.417 | 0.478 | 0 |
| F039/84 RX0 | 2 | 0.105 | 0.131 | 0.236 | 0 |

The original rank-0 candidate is selected for both peers. Neither alternative
produces a qualified evaluation frame. Thus choosing a different stored,
timing-compatible candidate does not rescue these paired decodes. This does
not rule out other calibration models, acquisitions outside this timing range,
or better observations elsewhere in the recordings.

The four candidate arrays, model/source hashes, discovery/evaluation metrics,
and selections are retained under ignored `local/peer-candidates/`. Two new
synthetic tests verify that evaluation outcomes cannot influence selection and
that ties follow the fixed rank rule. All 37 relevant tests and Ruff checks pass.
The bounded read-only run completed without new RF collection or decoded fields.
