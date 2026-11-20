# Distill capture-era GLRT winner families into the ordinary detector

Test whether an inexpensive score on the ordinary fast detector's existing
fractional candidates preserves capture-era GLRT winner families and reaches
within 5% or 10% of original v5 geographic error. Use the whole native stream
for each recording. Train on DS26-0036 and DS29-0082. Hold out DS26-0237,
DS29-0174, DS26-0122, and DS29-0247. All six recordings are from one roof.
Freeze the model and operating threshold before loading held teacher factors
or generating new position results. Include DS26-0144 and DS29-0491 as
supplementary held cases. Their existing whole fast streams use the wide
frequency roster. Apply the narrow-trained model unchanged and report these
two recordings separately as detector-range transfer.

Match identical valid probes from the bound fast and capture-era streams.
Within a probe, group duplicate candidates by complete-link epoch and CFO
distance. The strict tolerances are 0.2 microseconds modulo the rounded 750 Hz
frame and 1 kHz modulo the 1/(4.4 microseconds) CFO ambiguity. A capture-era
gate-passing winner supplies the positive label when its family has exactly
one fast-family neighbor and that family has exactly one capture-era neighbor.
Require the actual teacher winner to match at least one member of the fast
family. Other families in such a probe are negative. A probe with no teacher
winner contributes negatives. Omit ambiguous and unmatched teacher positives
from training and count each separately. Family membership is independent of
gate, score and rank. The fast representative maximizes the existing margin
with lower native rank as tie-breaker.

Fit a ridge-regularized logistic score with four nonnegative slopes. Inputs
are the fast representative margin, its margin minus the strongest rival
family margin, its negative control score, and negative log(1 + native rank).
Use zero as the rival margin for a singleton. Standardize the four features
from training only. Give the recordings equal weight, then usable probes in a
recording equal weight, then families in a usable probe equal weight. Use a
0.01 ridge coefficient on standardized slopes. The training mean of per-recording
shareable positive probe fractions defines the threshold operating point. Use
the midpoint between adjacent training scores closest to that prevalence and
prefer the lower threshold on exact ties. Rank and threshold held probes with
the frozen score. The enrollment, labels, weights and threshold are independent
of positions, orbits, recording date, and absolute RF as model inputs.

Compare unchanged stock and a strength control that admits the strongest fast
margin on exactly as many held probes as the learned rule admits. The learned
rule and strength control each mark one fast row per admitted probe. The matched
count is the number of probe winners handed to preprocessing. The retrospective
oracle chooses teacher-matched fast families; it keeps their original fast CFO
and epochs. The oracle keeps all definitely shareable winners, so its probe count
can differ. All variants preserve original rows and edit only private admission
flags. Neither the learned worker nor the strength ordering reads held teacher
factors. Compare to the historical univariate wide-margin admission experiment
as separate evidence.

Use the same installed compact-cut receiver, truth-free tile, track config,
causal TLE inventory, original clocks and search settings for all four variants.
Run one interleaved sequence per recording on CPUs 18 to 21. Give position workers
150 seconds, 512 MiB cgroup memory, zero swap, and one numerical thread. Report
gate time, compact stages, cgroup resources, valid probe counts, and terminal
failures. Raw-IQ detector costs come from the matched ordinary replay if present.
Do not add raw and solve wall times into a new measured end-to-end speedup.

Score after sealing predictions. Score both c = 0 and fitted-c publication,
per-recording 5% and 10% gates against no-repair v5, all four archived v5 roles,
conditional RF RMS, and position error. Report held family retention and
teacher-negative admissions separately. Treat the attainable family oracle as
a retrospective intervention on the available roster. Its outcome is a data
point for the coupled position solver.
