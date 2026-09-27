# DS6 fragment-offset consistency audit

This audit identifies repeated training-MAP catalogue candidates within the
same receiver, channel, and actual RF lane on the four frozen development
scans. It does not fit locations or establish physical satellite identity.
Only tracks with at least 0.99 conditional shortlist posterior mass enter a
potential link. Integer pilot aliases are aligned using training offsets.

| MS/s | Repeated groups | Tracks in groups | Longest combined span (s) | Shared-offset held log-score change |
|---|---:|---:|---:|---:|
| 2.5 | 2 | 4 | 53.4 | -72.59 |
| 5 | 3 | 7 | 82.8 | -34.11 |
| 7.5 | 5 | 10 | 59.7 | -98.52 |
| 10 | 0 | 0 | — | — |

Only 21 of 221 tracks enter these ten groups. At the existing frozen position
and timing, most groups lose held prediction when their separate offsets are
replaced by a single shared training-fitted offset. Aligned training offsets
differ by 9–641 Hz within groups. Nine of ten groups lose held prediction; one
improves by just 0.04 log units. The fixed-position audit therefore does not
justify blindly merging these fragments into a common-offset signal.

It also does **not** rule out linking followed by a location refit: a biased
baseline location can itself cause fragment offset differences. A proper next
test would freeze the training-derived assignments and alias shifts, compare
matched separate/common-offset arms, refit position, and evaluate unchanged
held visits. Any such test must retain the unlinked tracks and the scan without
links rather than redefine success around the few favourable groups.

The supplementary summary reports circular concentration of training offsets
modulo the RF-normalized pilot alias by lane. These concentrations are
conditional diagnostics, not a calibrated transmitter or receiver frequency
prior. No geographic reference was loaded by the audit or its summarizer.

Two tests cover integer alias preservation, source/input seals, exact group
membership, confidence gates, and reproducible alias assignment. These tests
validate the audit implementation, not the correctness of satellite labels.
All source files and results are retained. No RF or raw-IQ replay occurred.
