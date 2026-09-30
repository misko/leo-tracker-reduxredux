# Current decoding frontier after the DS10 follow-ups

The full goal—decoding more recorded symbols and determining what their bits
mean—is **not complete**. The previous combined-parity turn produced bounded
negative evidence. This continuation rechecked existing firmware and recording
evidence; it produced no additional decoded fields.

## Established outcomes

- Known T-code recovery extends into DS10. Its repeated signs do not count as
  independent new message bits.
- Simultaneous receivers support changing early structure. Within-visit frame
  comparisons distinguish it from a static pattern; identity remains conditional.
- Equal receiver averaging improves held-out known-tail sign recovery in three
  visits. Its confidence estimates are not validated for the early header.
- State averaging, local pair relations, neighbor prediction and amplitude tests
  have not established an additional symbol alphabet or transferable coding rule.
- The frozen public parity relation remains unvalidated after combining.

Detailed reports and generated receipts are in this directory. Source caches
and data outputs remain local and Git-ignored.

## Authoritative firmware and full-band findings rechecked

The current `../2026_09_28_sequence_semantics/SEMANTIC_CHECKPOINT.md` records
the GMH-to-RLC-to-control-message software chain and the completed upstream
descriptor trace. Its older reference-request blocker was superseded: obtaining
a labelled header is helpful, not a prerequisite imposed on further work.

`../../docs/research/starlink-literature/firmware-header-analysis.md` distinguishes
the decoded software bit-reader behavior from unverified RF serialization and
documents remaining CGM/configuration semantics. Neither a table name nor the
LSB-first software reader determines the OFDM bit mapping.

`../2026_09_28_sequence_semantics/FULLBAND_CONTROL_MESSAGES.md` records zero
validated direct matches for all four restricted RLC/PNT/SYSINFO layouts tested
against the public full-band material. Those tests do not exclude other layouts,
coding or fragmentation. The saved RLC, CGM and receive-buffer audit receipts
are still present; they do not supply the missing pre-descriptor PHY transform.

The observed software names SATAddr, RFNum and ephemeris fields are meaningful
targets, but none has been identified in our extra recorded signs. SATAddr must
not be equated to NORAD identity without evidence.

## Current impasse audit 1

There is no newly justified RF-to-MAC mapping hypothesis in the reviewed material.
Repeating field, parity or alignment scans on the same inspected frames would
not supply independent confirmation. The remaining bottleneck is a discriminating
PHY constraint: for example a verified encoder/interleaver or descrambler mapping,
a relevant firmware implementation/configuration with established semantics,
or a reference tying bytes to symbols. These are examples, not a demand for a
user-provided header or permission for new collection.

This is the first impasse audit after the recent DS10 progress. The goal remains
active, not complete; prior blocked counts are not reused. No process is being
waited on, no new RF is authorized or collected, and no result has been published
or committed during these follow-ups.

## Current impasse audit 2

The next continuation re-read the saved CGM alignment and variant receipts,
the full-band RLC probe receipt, and the latest sections of both firmware reports.
The prior turn is classified as no decoding progress, not a verified wait.
CGM setup bytes have a supported table-index interpretation, but table instruction
semantics remain unknown; variants use different tables. The RLC probe still
tests restricted contiguous layouts without channel decoding.

The latest header-report addition associates software prefix bits 4–5 with
PDU-sequence-map handling. This is a useful software constraint, but it explicitly
does not map to RF positions or establish the enumeration. The PNT serializer
also supplies synthetic software bytes, not a paired transmitted waveform.
Neither resolves the same pre-descriptor PHY transformation gap. No new justified
RF decoder hypothesis or pending analysis handle emerged from this recheck.

This is the second consecutive current impasse audit. Keep the goal active and
incomplete; do not count this status revalidation as additional decoding evidence.

## Current impasse audit 3

Re-read this checkpoint and the current combined-parity (six method/visit rows),
receiver-combining (three visits), raw-axis control (fourteen comparisons), and
full-band RLC probe results. They retain the recovery improvements and negative
mapping results described above. The previous turn supplied no new decoding
evidence and was not a verified wait. No result now supplies a verified
symbol-to-byte transform, additional field, or independently justified decoder
hypothesis that removes the same obstacle.

The same impasse has now persisted across three consecutive current audits.
Mark the goal blocked, not complete. Resume on a discriminating coding/mapping
constraint or other concrete hypothesis with a falsifiable independent check.
This is a limit of the present investigation, not proof that decoding is
impossible or that a private reference is required. Existing online-source-only
and no-new-RF constraints remain respected.
