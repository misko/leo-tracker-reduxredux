# Independent two-refresh compact v5 confirmation

Run `v5_two_refresh` through the paired compact v5 cavity decision. The worker
uses the complete archived native GLRT detections, original 25 km tile and
causal orbital catalogue. Retain the original branches, observation set,
calibration arms and decision gates. The sole candidate is the two-refresh
budget chosen before these confirmation coordinates were scored.

Form the confirmation cohort from the 127 common DS26 recordings and eight
DS29 roof recordings. Exclude the existing six timing recordings. Sort the
eligible DS26 IDs by the SHA-256 of `phase-refresh-confirm-v1:` followed by
the UTF-8 ID and select the first 16. Include all five eligible DS29 IDs.
The selection uses no positions, errors, or branch-rank outcomes.

| Group | Frozen recording IDs |
|---|---|
| DS26 in hash order | DS26-0142, DS26-0223, DS26-0301, DS26-0018, DS26-0201, DS26-0177, DS26-0068, DS26-0233, DS26-0215, DS26-0040, DS26-0162, DS26-0311, DS26-0152, DS26-0078, DS26-0080, DS26-0261 |
| DS29 | DS29-0127, DS29-0316, DS29-0357, DS29-0519, DS29-0604 |
| Prescheduled timing, reported separately | DS26-0036, DS26-0122, DS26-0237, DS29-0082, DS29-0174, DS29-0247 |

Run all 21 confirmation recordings with the same frozen source regardless of
the behavior of the six timing runs. Use the standard worker on CPUs 16–19,
with at most four active workers, one numerical thread per worker and a
480-second worker deadline. Keep every attempt and its actual elapsed time,
including timeouts, failed and withheld results. Keep the timing cohort's
paired modern compact measurements separate. The confirmation stock
positions come from the authenticated original 135-recording projector
archive and its exact matching input. Archived times are historical.

Seal the confirmation predictions and their sources before opening any
position references for this cohort. Verify the exact native, catalogue,
request and tile match to the compact projector and the original four v5
options. Report independent-reference position errors and coverage by
dataset and calibration arm, including published distributions, matched
per-case differences, and the counts at 1, 2, 5 and 10 km. Report conditional
frequency RMS separately from position accuracy. The timing cohort reports
fresh paired elapsed time and remains separate from confirmation accuracy.
No RF is collected.
