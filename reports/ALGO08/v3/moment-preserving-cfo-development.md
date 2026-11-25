# Development screen for polynomial-preserving CFO edits

The projection improved strict same-capture carrier agreement on all
four development recordings, adding eight matches in total. It retained
2.000 million Hz² of signed edit energy. The original half-blend added
47 strict matches on these same denominators. The frozen development
screen permits one RF-only comparison on held rank 68, DS30-0280.
[Frozen rule and enrollment](moment-preserving-cfo-protocol.md) ·
[Development receipt](measurements/moment-preserving-cfo-development.json)

| Recording | Installed matched / proposed | Empty | Surviving edits | Retained edit energy | Strict unedited / projected / previous | Projected restored / spoiled | p95 absolute Hz, unedited / projected / previous |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0019 | 355 / 366 | 11 | 181 | 16.3% | 322 / 323 / 340 | 4 / 3 | 306.86 / 306.86 / 236.29 |
| DS30-0274 | 484 / 499 | 15 | 373 | 23.7% | 457 / 459 / 463 | 5 / 3 | 261.35 / 252.93 / 206.68 |
| DS30-0218 | 522 / 530 | 8 | 376 | 22.9% | 483 / 487 / 499 | 5 / 1 | 307.58 / 307.58 / 232.91 |
| DS30-0212 | 150 / 153 | 3 | 73 | 15.3% | 138 / 139 / 145 | 1 / 0 | 316.89 / 316.89 / 204.11 |

The loose counts held at 347, 472, 506 and 145 for all three change
conditions. The strict and loose windows retain the original signed
250 Hz / 2-sample and 2,250 Hz / 6-sample rules. Every original edit
opportunity remains in coverage. The projected p95 absolute difference
decreased visibly on DS30-0274. [Prior carrier readouts](masked-cfo-0212-installed-agreement.md)

The ordinary Graph replay reproduced each archived assigned and track
count. The original piece degree ranged from one to four across edited
tracks. The projection preserves each ordinary track's fitted Legendre
model span, including the released continuity constraints of joined
pieces. For a fixed support and alias lift the stored deltas are
orthogonal to the fitted design columns, so the unweighted least-squares
trend is preserved within binary64 precision. The largest orthonormal
moment after applying the stored CFO was 6.83e-11 Hz, within 9.3% of the
respective numerical bounds across all tracks. Eighteen edits had
unassigned ordinary winners. Tracks without sufficient independent
edited support and tracks whose modeled span occupied every edited
coordinate received zero changes.

Physical CPU 3 time was 7.16 seconds for the four-case offline audit.
The projection itself used 4.5–11.4 ms CPU per case. Rebuilding the
ordinary Graph used 0.541–1.464 CPU seconds per case, in addition to any
masked Graph edit reconstruction. Ordinary assignment is a prerequisite
for the projection. This audit ends at the frozen signed measurements,
before any corrected Graph or position fit. Nine focused tests passed.
[Runner](moment_preserving_cfo.py) ·
[Tests](../../../tests/pipeline_eval/test_moment_preserving_cfo.py)
