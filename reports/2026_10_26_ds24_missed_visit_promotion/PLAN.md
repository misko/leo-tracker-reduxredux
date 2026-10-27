# Frozen missed-visit recovery: promotion evaluation

Requested by the user on 2026-10-26. SOL high workers perform acquisition,
regional position fitting and independent evaluation. This study uses existing
recordings only; QNAP remains read-only and no new RF collection is authorized.

## Decision

Test whether the demonstrated R01 recovery application warrants a new ALGO.
The primary comparison must improve reserved-scan median position error by at
least 10%, with no increase in p90 and no reduction in qualification coverage,
in both c=0 and fitted-c arms. Report all intended scans, failures and caps;
complete-case results alone cannot satisfy the coverage requirement. Frequency
RMS, acquisition coverage, track membership and satellite association are
separate outcomes. No promotion based on the two favorable development scans.

## Frozen operational application

R01 is the unchanged earlier-history timing search. R02 is not a candidate in
this evaluation. The initial sparse panel is used to nominate longer blocks:

1. Apply the original fixed CH1/4/5–8, four-counter-fraction, both-RX panel.
2. Use original observations plus admitted R01 sparse additions to identify
   new actively curved CH5–8 graph support.
3. Apply the exact prior coherent block selection: rank lanes by new curved
   support, then new native support, channel and receiver; take at most two
   eligible lanes per recording, and the earliest qualifying seed per lane.
4. Include processed visits in each closed seed-centered 24-second interval,
   both receivers, retaining the original 80-window-per-block bound and exact
   native ownership. Deduplicate overlapping native windows.
5. Reuse the frozen R01 forecast, adapter, timing search and independent
   confirmation. Donors are strictly earlier ORIGINAL observations. No
   recovered-donor feedback, R02 mixing or target-driven parameter changes.
6. Regional candidate inputs are all original observations plus admitted
   coherent-block additions ONLY, matching the previous 0011/0097 application.
   Sparse-only additions outside those blocks are not silently unioned in.
   A scan with no eligible lane retains its original inputs and stays in the
   intended-cohort denominator. An unavailable/failed block is not a success.

Use the serialized v2 forecast enrichment boundary. Reuse previous blocks only
after source, input, ownership and protocol equality verification.

Primary weighting floors NEW observation uncertainty at one full frequency bin
(443.892045 Hz), without changing original CFO/margin values. Graph-derived
proxy weighting is a separately reported secondary sensitivity. Never choose
between those variants using geographic error. Track rebuilding may change
incumbent graph membership and learned noise scales; report those effects.

## Cohorts and position inference

Reserved DS24: 0015,0016,0019,0075,0077,0081,0083,0085,0089,0091,0093,0095.
Previously exposed development DS24: 0010,0011,0012,0013,0014,0017,0018,0079,
0087,0097,0099,0101. These are the already frozen 24 usable recordings; retain
the ten unavailable inventory members as explicit scope limitations. The
reserved split is held only from this revision, not from all earlier research
and not from a different geographical site.

DS23 is a separate regression cohort. First inventory native/runtime authority
and availability without geographic error-based selection. Fix a bounded,
representative compatible panel before recovery outcomes. Do not substitute
DS24 results, historical different algorithms or no-addition identity replays
for a DS23 recovery validation. Full multi-hour raw campaigns are out of scope.

Position inference retains the original 25x25 km region centered at
37.906,-122.545, start east/north 0/0, full causal TLE catalogue, causal signed
phase prior and equal-prior family cavity. Each job contains matched c=0 and
fitted-c observations, candidate sets, other priors and search budgets. No
post-scan TLE, fixed satellite shortlist or ground-truth seeded inference.
Evaluation coordinate 37.849061591561885,-122.48574968092912 is used only after
input/source, terminal output and inference-read audits have been sealed.

Initially allow four numeric position workers and two raw replay workers,
BLAS1. Raw shards retain 580-second caps; regional jobs retain 240-second total
numerical caps. Infrastructure-only continuation requires preserved attempts,
verified source/input identity and remaining-budget accounting. No numerical
outcome-based retry or cap reset. If inputs are identical, a sealed baseline
can supply a zero-addition control with explicit equality proof.

## Scope correction before geographic evaluation

Workers were initially asked to fit sparse-only R01 additions. Before any new
geographic outcomes were opened, root corrected the primary input to the exact
coherent 24-second application that produced the previously reported gain.
The sparse-only held worker had dispatched 36 jobs; all failed during imports
before numerical discovery. Their protocol, receipts and outputs are retained.
They are not successful primary runs. No geographic metric motivated the
scope correction, which prevents confusing sparse sampling with a test of the
demonstrated longer-segment application. The implementation environment must
be checked through the full directory-binding import path before relaunch.

## Deliverables

Per-scan errors, qualification/failure status, GLRT and graph/satellite counts,
family changes, frequency RMS, runtimes, paired error distributions and a
promotion decision. Independent auditing precedes reference-error reporting.
Publish an MD report with figures, tables, exact sources/protocol hashes and
scope limitations to remote main. Keep the current ALGO default unless the
predeclared scientific and coverage requirements are met. This is evaluation
of one frozen recovery method, not another hyperparameter search.
