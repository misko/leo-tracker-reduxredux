# Candidate-conditioned cross-RX residual slope transfer

Frozen before execution. Reuse nine eight-scan target exports, all 3,983 eligible
conditional residual cases. For each target, seek opposite-RX tracks assigned
to the same candidate number, same recording and exact RF. Require 50% overlap
of target training span and five donor training points spanning five seconds
within that span. Median the donor training slopes; one donor suffices because
the hypothesis is transfer of a particular candidate's residual, not a population
clock estimate. Exclude target track. No held samples estimate a donor slope.

Controls: zero slope; own training slope; opposite-RX other-candidate slope,
median within candidate then across at least one distinct other number with the
same RF/overlap/sample requirements. Report primary support independently and
compare donor arms on their matched subset. All use target training time and
residual means, and score median absolute held residual. Unsupported arms remain
at zero slope in full-population accounting. Record every donor track/number.

This tests candidate-conditioned shared residual structure, not satellite truth.
Both RX residuals inherit the same fitted geographic and recording-time errors;
agreement cannot distinguish orbit error from incorrect location, common signal
processing, transmitter effects or association. No geographic promotion from
this assay alone. No RF, production edits or changes to membership/thresholds.
