DS23-0365 exact offending native path diagnostic
==============================================

Selection uses the sole failing RF gate from the matched optimizer comparison:
GRAPH_PATH_persistent5s_005, NORAD 68553, candidate 1289, RX1 / channel6,
12.1903125 GHz, 40 native GLRT observations from 44.975829 to 95.032730 s.
No GPS selects this path. It has no overlap with the 2,073 accepted graph-parent
IDs and is not an original predictive entry.

At full-mask ordinary endpoints the path's profile-innovation lag-one ACF is
0.633511701 / 0.632839142 (c0 / fitted_c), exceeding the unchanged threshold
4/sqrt(40) = 0.632455532. At constrained endpoints it is 0.626888716 /
0.628138066. results.json includes every CFO, canonical track value, raw
prediction residual, mean-centered raw residual, profiled innovation, gate
statistic and threshold. Centered raw residuals are visualization diagnostics;
the acceptance noise screen uses the existing profiled innovations.

The ablation removes exactly this whole newly added path and retains all other
entries, the original curved mask, identities, aliases, priors and gates.
Existing ordinary cold [0,0] fits use zero starting phase references and five
rounds of 48 Gauss-Newton iterations in both arms. Fits took 4.44 / 2.98 seconds
under individual 180-second caps.

Both reduced-mask fits qualify: minimum gate slacks 0.039372 / 0.045781, phase
changes 0.000690 / 0.000622 seconds. They preserve every accepted parent ID and
associate 2,194 observations, a gain of 121 over the parent. Reporting-only
position errors are 0.529120 / 0.670890 km. These are diagnostic evidence about
this exact RF-identified path, not a proposed production pruning policy.

On the common full mask, these same endpoints fail only the removed path's
lag-one gate, with slacks -0.003398 / -0.001832. Full-mask objectives are
21964.558976 / 21969.290402, close to the full-mask ordinary endpoints'
21964.494973 / 21969.245846. Reduced and full objectives use different data and
must not be directly compared. The other recovered native points remain useful
under the original qualification gates without this path; the path's marginal
RF gate failure can induce the large displacement seen in constrained rescue.

No production behavior changed, no thresholds relaxed, no original observations
removed, no new RF collected, no old artifacts modified. GPS appears only in
report.py after fitting. Two owned tests pass in 2.00 seconds, checking exact
entry exclusion, original ID preservation, fit rounds, and the actual residual
length/lag-one threshold against both full-mask endpoint types.

Use the same PYTHONPATH and interpreter as the parent solver0365/README.md.
Run run_followup.py, report.py, and pytest test_followup.py in that order.
