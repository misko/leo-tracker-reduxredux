# Independent terminal-report verification

The existing [RESULTS.md](RESULTS.md), numerical summary and qualification PNG
were reviewed without altering their authoring source or performing numerical
evaluation. The negative result is accurately represented: iteration96's selected
prefit qualified at0.000845178642, but iteration95's corrected fixed-position
postfit was unqualified at0.016400970241. Optimizer success is separate from
independent qualification. The saved228 evaluations and0.620s do not indicate a
20-second timeout.

| Stage | Observed disposition |
|---|---|
| Prefit selection among six persisted states | Completed; qualified iteration96 chosen by lowest same-model objective |
| Receiver correction and corrected postfit | Attempted; corrected postfit unqualified |
| Association | Not reached |
| Fitted-c and c0 regional finals | Neither reached |
| Regional winner comparison | Not reached |
| Ordinary-only B7 replay | Not reached; fresh baseline parity unmeasured |
| Candidate B7 continuation | Not reached |

Exactly one saved continuation stage exists, `recovered-calibration`. Its payload
matches the terminal result and numerical summary. All682 frozen closure hashes
pass. [verification.json](verification.json) records every original stage receipt
hash and hashes the result, report, summary, protocol and inspected PNG.

The archived55.685054km fitted-c and53.945451km c0 results remain the only final
positions here. No new positioning, matched-c downstream comparison, rescued
region winner or fresh B7 parity was measured. The corrected postfit objective
uses a changed receiver-calibration baseline and cannot be compared directly to
the uncorrected prefit objective as a localization improvement.

The existing plot clearly marks the second qualification failure and labels both
position bars as archived. A separately frozen iteration97 may apply the unchanged
iteration96 rule to this corrected objective. That next test is needed to establish
whether its failure shares the prefit mechanism; this report does not assume the
answer. Production and closed reserves remain untouched.
