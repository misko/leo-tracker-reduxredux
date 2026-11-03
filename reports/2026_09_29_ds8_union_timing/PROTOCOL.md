# DS8 N40 endpoint timing diagnosis

The previous two qualified N40 endpoints remain 273 m apart. At each fixed endpoint, replay each scan and refit its timing from three predeclared starts: its own endpoint timing, the other endpoint timing, and the best training score on the unchanged 41-point timing grid. Select only by qualified training score. Preserve all starts and failures. Do not use held observations or reference distance in selection.

Compare per-scan training/held scores, timing changes, and conditional-signal top-candidate changes before and after timing reselection. Verify aggregate replay of both prior fits, input digests, and identical track membership. Run on the same forty cached scans, with a 180-second cap and no silent retry. No new RF, exports, candidate propagation, model changes, or production edits.

If timing reselection materially improves training score, a subsequent declared joint refit may test whether it removes the endpoint disagreement. This diagnosis alone is not geographic validation and does not establish a true satellite identity or global optimum.
