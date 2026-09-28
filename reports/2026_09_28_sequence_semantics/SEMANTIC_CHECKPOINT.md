# Semantic decoding checkpoint

Latest local progress: [short-header probes](SHORT_HEADER_PARITY.md) tested
frequency prefixes with inferred parity masks and arbitrary within-symbol starts
with an assumed 133/171/165 convolutional code. Neither supplied a validated
decoder; the latter's discovery-selected candidate had 46.7% evaluation syndrome
errors. Public firmware inspection obtained a Linux partition but found no PHY
or lower-MAC runtime binaries. APK bundle acquisition remains unresolved.
These are completed bounded investigations, not running jobs or proof that a
known header is required. The full semantic-decoding objective remains incomplete.

Update 2026-09-28: the user requires public online sources only. The historical
reference request and blocker audits below are superseded as a work dependency:
a known header would help validation but is not a prerequisite for further work.
A public APK teardown reports embedded dish firmware bundles, providing a new
static-analysis lead. See [firmware source review](../../docs/research/starlink-literature/firmware-leads.md).
Acquisition, binary contents, and relevance to the radio header remain unverified.

The objective remains to decode and understand the additional header and short
tail regions. It is not complete. This checkpoint follows the 21-test analysis
suite and the expanded 20-frame full-band sample (seven raw-IQ-derived frames
and thirteen published hard-symbol frames).

Validated evidence includes the 60-state tail alphabet, pilot-referenced header
signs, matching sampled published decisions, and the observable low-phase LFSR.
The exact high-plane template representation does not uniquely identify the
transmitter descrambler. Counter, copy, and short-parity models have not provided
verified fields or an error-corrected header. Strong receiver agreement alone
also admits short-window discrepancies.

The current bottleneck is a discriminating header reference: a known transmitted
header paired with its symbols, a concrete encoder/interleaver definition, or
an implementation that supplies an independently checkable test vector. A user
question requesting an existing reference is pending. No new RF collection is
authorized or planned.

Blocker audit 2: rechecked the checkpoint, latest result files and literature
notes on the next goal continuation. No new labelled header, encoder/interleaver
definition or decoder reference is available, and no analysis process remains
pending. The reference question has not been answered. This turn supplies no
new decoding evidence; the same semantic-validation bottleneck remains. Keep
the goal active for now; neither completion nor the three-turn blocked threshold
has been established.

Blocker audit 3: the next continuation revalidated the checkpoint and unchanged
result files. No reference response or new discriminating evidence is available.
The same missing semantic-validation reference has persisted for three consecutive
audits. Mark the goal blocked, not complete. Resume when a known header test
vector, concrete coding/layout definition, or independently checkable decoder
becomes available. The published report and local datasets preserve the work.

Do not count another parameter sweep on the same inspected frames as independent
confirmation. To resume with a new hypothesis, state what evidence distinguishes
it from the existing alternatives, fit on discovery material only, and verify
an actual field or coding constraint on unused observations. More unlabelled
frames can improve statistics but do not by themselves resolve an arbitrary
fixed-mask/unknown-data ambiguity.
