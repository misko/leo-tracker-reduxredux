# Full148 frequency-width experiment complete

Completion update: all148 terminal receipts and592 raw fits are complete and
independently qualified, with no fallback. Sessions60178/22011 have exited0;
the earlier38325/21253 are also terminal. No duplicate launch is needed.
Both arms fail the predeclared gates. See [the decision](DECISION.md),
[full results and plots](RESULTS.md) and [raw archive](RESULT_ARCHIVE.md).
Production is unchanged; the0.4 km objective remains active and unachieved.

The historical progress record below is preserved; its running counts and
session status are superseded by this completion update.

The preceding goal turn made verified progress: iteration105's generic five-case
recovery pilot completed and was published with plots and all receipts in
9837dd91c. It repaired the already consumed ac11 failure and left the other four
results unchanged. It did not establish a full-dataset mean improvement or the
0.4 km goal.

Iteration106 was frozen and pushed in cf7f22373 before any recording evaluation.
All16 preflight tests passed. The protocol includes every DS16/DS17/DS18 member
(63/51/34), four matched fits per member, fixed125/100 Hz widths, independent
qualification, unchanged budgets and explicit fallbacks. Production is unchanged.

The first bounded batch completed16 members and all64 fits qualified. The two
continuation controllers are processing the remaining132 members using the same
frozen protocol. At the latest verified check,40/148 members had complete terminal
receipts and all160 corresponding fits qualified. No position-error report has
yet been evaluated; full-census accuracy and decision gates remain unproven.

## Continuation handles

Tools sessions60178 (shard0) and22011 (shard1) were confirmed live during this
progress update. Poll these exact handles before deciding whether work stopped.
They each invoke the controller with `--maximum-members 74`; already complete
members are skipped, and immutable launch claims prevent implicit crash retries.
Do not start duplicate workers. Earlier batch sessions38325/21253 are terminal.

The report helper and tests are prepared, including per-binding frozen evaluation
metadata, explicit missing/failure rows, matched control comparisons, frequency
effects, runtime and plots. Run it with `--evaluate-sealed-results` after terminal
coverage is inspected. Preserve every raw failure and distinguish raw qualification
from fallback-qualified operational outcomes. Never compare scores across widths
to select a winner.

Iteration107 separately resolves all193 recovery-study members and documents why
46 historical DS16 baselines need current-policy reconstruction. Its source
coverage report and old-coarse-only proposal are preparation, not a new accuracy
result or a blanket permission to reuse old pipeline stages. Full recovery-driver
implementation is continuing; no107 numerical experiment has started.

No RF collection, reserve access, QNAP mutation or production change occurred.
The full0.4 km mean-error objective remains active and unachieved.
