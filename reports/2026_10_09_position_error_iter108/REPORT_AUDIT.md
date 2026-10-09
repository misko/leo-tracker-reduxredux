# Independent completed-census audit

All 2,314 frozen source hashes match. Every one of the 148 protocol members has
a complete, matching-protocol receipt with both arms: DS16 63, DS17 51, DS18 34.
There are no missing or failed members. Independently recomputed all six
dataset/arm row counts, linked fractions, row-weighted entropy, confidence bins
and switch totals from receipts; they match summary.json. No optimizer or
recording reconstruction was invoked for this audit.

There are 429,788 observations, 187,506 linked rows (43.6276%) and 179,540
eligible adjacent links. Linked rows with maximum categorical probability at
least 0.9 comprise 92.7048% in fitted-c and 90.8643% in c=0. Fitted-c has
6,311 changed top labels (3.5151% of links), including 449 switches between two
confident satellite labels. c=0 has 9,231 changed labels (5.1415%), including
465 confident satellite switches. These are categorical model summaries,
including clutter; confidence does not establish satellite assignment correctness.

Saved objective reconstruction differs by exactly zero in both arms. Independent
rho=0 score nesting differs by at most 7.275957614183426e-12; prediction-gradient
differences are exactly zero. Thus the descriptive census passes its numerical
parity checks. Inherited reference-bearing provenance admission remains disclosed;
reference values do not guide grouping or this audit's statistics.

## Recommendation

Only a bounded, separately frozen conditional trial is justified at present.
Most linked rows already have concentrated independent categorical probabilities,
and fewer than half of all observations have eligible continuity. That leaves a
limited opportunity to change weak or unstable labels. Confident switches may
represent real transitions, grouping imperfections or model mismatch; suppressing
them is not automatically beneficial. No position-accuracy or calibration claim
follows from these counts.

Use the marginal-preserving iteration109 transition if testing persistence,
after full composed gradient/lock tests. Predeclare a small global comparison,
matched c arms, inference-only grouping, equal starts/budgets, complete failures,
runtime/memory and position evaluation separately from sequence fit. Avoid a
substantial parameter sweep, scan-specific rho choice or operational deployment
based on this census. This is consumed-data mechanism development, not independent
validation of a new localization method.
