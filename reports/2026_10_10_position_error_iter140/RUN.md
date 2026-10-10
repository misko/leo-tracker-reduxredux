# Full phase comparison: execution receipt and assessment

The single serial worker, session 85422 (batch PID 1368740), terminated with
exit 0. All 193 frozen members have complete terminal receipts and exclusive
claims bound to protocol
`1c5c86cd48e1aa8bd5fa37634989229f36b4eb970f699935fc9f939e577f1387`.
All 386 result/claim files were independently checked, with no extra or missing
files. There were 772 returned fits: 770 qualified and two retained unqualified.
No restart, retry, additional fit or production change occurred.

| Unqualified member | Variant/arm | Independent stationarity | Feasible | Minimum physical constraint | Solver success | Seconds | Evaluations |
|---|---|---:|---|---:|---|---:|---:|
| POST18-NEWER-20261009-001 | phase/fitted-c | 0.001164638309 | yes | 15.24987961 | yes | 5.807967 | 206 |
| POST18-NEWER-20261009-045 | phase/zero-c | 0.002010269815 | yes | 17.64408583 | yes | 4.029917 | 193 |

Both exceed the unchanged 0.001 stationarity gate despite optimizer success.
Neither is silently accepted. Strict full-cohort phase metrics are withheld;
the full-coverage comparisons below are the report's explicitly separate
**archive-fallback sensitivity**, with one fallback per c arm. They do not
establish all-member phase qualification.

| Dataset | Count | Fitted-c timestamp mean km | Phase sensitivity mean km | c=0 timestamp mean km | Phase sensitivity mean km |
|---|---:|---:|---:|---:|---:|
| DS16 | 63 | 0.973596 | 0.903642 | 1.328279 | 1.243023 |
| DS17 | 51 | 0.819111 | 0.794122 | 1.328547 | 1.302181 |
| DS18 | 34 | 2.691656 | 3.085888 | 2.835941 | 2.792613 |
| Newer development | 45 | 1.056687 | 1.009976 | 1.743946 | 1.742003 |
| Full | 193 | 1.254810 | 1.283931 | 1.690866 | 1.647983 |

Fitted-c median improves from 0.892565 to 0.828960 km, but the mean worsens and
the worst case increases from 53.400741 to 67.124341 km. DS18-022 contributes a
13.723600 km paired regression. Among the 192 qualified fitted-c pairs, 135
improve and 57 regress, with one regression over 1 km. In c=0, 127 qualified
pairs improve and 65 regress; two regress by over 1 km, with maximum 2.228685 km.
The full c=0 sensitivity median is 1.150143 to 1.068418 km. Improvements in
typical cases do not justify deploying this variant with these failures and
tail regressions. The 0.4 km standalone mean goal remains unmet.

Timestamp fitted-c reproduces the archived selected baseline to numerical
precision. The c=0 timestamp control can differ from its archive because both
fresh arms deliberately share the fitted-derived start, with c=0 RF locks.
Interpret phase effects against that matched timestamp control, not solely the
historical archive. Separate likelihood/prior/assignment effects are retained
in the evaluation; frequency-fit changes are not positioning evidence.

Summed member elapsed time is 4,890.405179 seconds, including reconstruction and
four fits per member. This is not cold production latency or an embedded-speed
measurement. Reporting started only after the authoritative worker exit and all
193 terminal receipts. The report process (56367) and archive process (72080)
both exited 0. The comparison PNG was rendered and visually inspected; all six
report artifact hashes were independently checked.

The verified deterministic raw archive is 76,559,694 bytes, SHA256
`d2c98e0161857a64947f3f7a6c4cf2f6111e71c9b423808141a7845303f3fef5`.
Original raw files remain in place. `RESULT_ARCHIVE.json` preserves every
archived file digest, and `report-integrity.json` binds the evaluated receipts
and report artifacts. No repository merge or publication was performed by this
worker while frozen jobs were running; publication remains coordinated through
the parent's isolated report worktree.
