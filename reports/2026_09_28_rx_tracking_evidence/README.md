# Evidence for receiver-order tracking tests

**Both evidence exports are complete, and every held-frequency observation joins to its recorded receiver opportunity.** The main finding is a partitioning problem to fix before a detection-order model: the original per-track frequency masks share source support across tracks.

This package continues the [temporal geometry pilot](../2026_09_28_rx_beam_crossing/REPORT.md). SOL built and audited the frequency extraction; Terra built the paired-opportunity exporter and audited its interpretation. The coordinator froze and ran both extractors serially, checked joins, and recorded the results. No new reception model was fitted and no accuracy improvement is claimed.

## Completed evidence

| Product | Result |
|---|---:|
| Recorded paired observation windows | 22,155 |
| Receiver probe bindings | 44,310 |
| Windows with candidates on both receivers | 11,697 |
| Windows with candidates on exactly one receiver | 4,858 |
| Windows with no passing candidates on either receiver | 5,600 |
| Public projected source candidates | 81,390 |
| Reconstructed held-frequency observations | 10,369 |
| Associated tracks / recordings | 599 / 10 |
| Held observations joined exactly to existing reception rows and source opportunities | 10,369 / 10,369 |

The opportunity counts reconcile exactly, with no missing, duplicate, inconsistent or unqualified receiver windows in this export. Candidate presence on both receivers does not establish that both detected the same satellite. Completeness covers the recorded 20 ms probes, not continuous RF reception between probes.

The frequency reconstruction reproduced original candidate IDs, training masks, profiled training errors and probabilities, snapshot/evidence hashes and source timing. Its fixed Gaussian scale is 100 Hz, as in the original association calculation. No held measurements were used to profile CFO or choose candidates. This is reproduction of a historical reference-conditioned hypothesis bank, not fresh satellite identification.

## Source overlap found

| Audit | Count | Meaning |
|---|---:|---|
| Training–held overlapping signal-interval pairs | 1,421 | Same session, source group and receiver stream; every pair crosses tracks |
| Distinct held observations involved | 1,395 / 10,369 (13.45%) | Their signal support overlaps training support in another track |
| Paired probe windows containing both training and held observations | 4,696 | Broader cross-receiver/window grouping |
| Held observations in those mixed paired windows | 5,485 / 10,369 (52.90%) | Conservative window-level dependency flag |
| Held observations outside original training paired windows | 4,884 | Diagnostic eligibility count, not an independently validated replacement cohort |

The narrow interval audit compares half-open sample intervals only within the same session/source-group/stream; 23 pairs have identical intervals. The broader paired-window audit can group different signals, so it is a conservative dependency warning rather than proof that every grouped observation concerns the same target. These checks establish that the old masks are not globally source-independent; they do not establish how much any previous metric was affected. Simply deleting flagged rows would change the endpoint and would not remove reference conditioning or full-record track selection.

## Artifacts and reproduction

- [Paired opportunity rows](opportunities/opportunities.jsonl), [source bindings](opportunities/source-bindings.jsonl), [export summary](opportunities/summary.json).
- [Held-frequency evidence and complete original masks](held-frequency.json).
- [Exact join audit](join-audit.json), [reproducible join audit script](audit_join.py), [per-held-observation overlap flags](held-window-eligibility.jsonl).
- [Signal-interval overlap audit](frequency-overlap.json), [reproducible interval audit script](audit_frequency_overlap.py), [opportunity feasibility audit](OPPORTUNITY-AUDIT.md).
- [Frequency launch](frequency-launch.json) and [resources](frequency-resources.txt): exit 0, 118.62 seconds, 498,668 KiB peak RSS.
- [Opportunity launch](opportunity-launch.json) and [resources](opportunity-resources.txt): exit 0, 26.22 seconds, 557,288 KiB peak RSS.
- [Frequency extractor](../../tools/rx_held_frequency.py), [opportunity extractor](../../tools/rx_paired_opportunities.py), [frequency tests](../../tests/research/test_rx_held_frequency.py), [opportunity tests](../../tests/tools/test_rx_paired_opportunities.py).

Both runs used one numerical thread, nice 19, a 4 GiB address-space ceiling and a 300-second deadline. Eight focused component tests passed; Ruff passed. No raw IQ, new RF collection or geographic fitting was performed. The opportunity candidate contract has a receiver ID rather than a graph stream ID; the optional source-interval stream field is null, and the join explicitly verifies the graph label `rx-{receiver_id}`.

## Next experiment requirements

The paired-opportunity product covers recorded probe windows, including valid windows with zero passing candidates. Its satellite identity is deliberately unassigned. The frequency product reconstructs the original candidate-specific held-frequency likelihoods, profiles constant CFO using training observations only, and preserves source intervals and masks for later leakage checks.

[PROTOCOL.md](PROTOCOL.md) fixes the scope and extraction limits. Each completed launch has a separate command/hash receipt, terminal log and resource report. [runtime-binding.json](runtime-binding.json) records the installed historical analysis code and numerical library versions.

The next detection-order experiment must define its target hypotheses independently of the detections being scored. It must also keep Doppler training, reception conditioning and held-frequency targets separated by source window across both receivers. Recovering a held-frequency likelihood does not itself make it independent of reception evidence from that same window.

Concretely: group source windows across receivers and tracks before partitioning; construct a candidate prediction bank from the training partition only; predict candidate frequency/visibility into the remaining recorded windows; and score reception conditioning and frequency targets on separate windows. Only then compare a receiver-order or calibrated lag model against the static geometry/OU baseline. The current exports supply the identities, measurements, timing and overlap flags needed to implement that test, but do not manufacture target-level absent events.

All ten recordings remain reference-conditioned and research-exposed. Future sample-rate coverage must be addressed explicitly: the only 7.5 MHz recording cannot provide both independent training and evaluation examples. A new split of these recordings is exploratory, not blind confirmation.
