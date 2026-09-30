# Remaining decoding constraint: resumed-goal audit

## Audit 1 — September 29, 2026

The preceding turn completed the combined report and verified its evidence;
that was progress. This turn rechecked public mapping leads against completed
firmware work. It found no new independent constraint or executable decoder
hypothesis. Repeating previously rejected scans would not resolve that gap.
This is the first current impasse audit, not a continuation of an older blocked
goal's count. The app goal remains active and incomplete.

Public searches used `Starlink downlink header decoding SATAddr PHY MAC reverse
engineering` and `Starlink OFDM physical header decoding scrambling interleaving
2026`. This was bounded source discovery, not an exhaustive proof about everything
online. The apparently relevant July 2026 discussion was already catalogued in
`docs/research/starlink-literature/firmware-leads.md`:

- The [first-person header question](https://www.reddit.com/r/StarlinkEngineering/comments/1v9rfdl/starlink_ku_ofdm_phy_pdu_header_which_res_to_take/)
  asks for unresolved resource-element placement, code and interleaver details.
  Its accessible reply offers opinions rather than a validated mapping. It is
  not independent confirmation of a proposed decoder and supplies no new test
  vector for this investigation.
- [Quarkslab's current tool inventory](https://github.com/quarkslab/starlink-tools/blob/main/README.md)
  lists partition extraction, memory-ECC removal, gRPC, runtime emulation and IPC
  tools. It does not list a downlink RF-to-MAC decoder. Memory-image ECC is not
  evidence for the air-interface coding scheme.
- The already reviewed waveform paper remained the relevant technical search
  result; no newly verified semantic header decoder was identified.

The existing firmware report was re-read at its 32-bit/114-symbol MCS entry,
descriptor-to-payload distinction, CGM table/index correspondence and hardware
variant comparison. These provide software structure and candidate constraints,
but still do not establish the encoder, scrambling/interleaving, carrier placement
or hardware table semantics needed to predict actual recorded header bits.
The earlier constrained tests of these numerical leads remain negative; this
review does not justify rerunning them.

The same unresolved constraint affects two desired end results:

1. **Semantic decoding:** no verified relation from the recovered early waveform
   to the software header fields, including SATAddr.
2. **Empirical identity:** current controlled tests lack a robust, repeatable
   signature that separates satellites from time/beam/channel state and uncertain
   orbit associations. The fixed simultaneous prototypes produced only one usable
   paired visit, and its contrast was uninformative.

No new RF collection or private source access is assumed. No semantic field has
been recovered. A new independent public mapping/test vector, or an independently
justified discriminating experiment on the existing recordings, is needed to
restart meaningful decoding work. Merely increasing scan counts or relaxing
quality gates is not such a constraint. No goal status change is made at this
first impasse audit.

## Audit 2 — saved results and unfinished-work check

The preceding audit did not advance decoding; classify it as no progress, not
a verified wait. Reinspection of the current saved results confirms that both
simultaneous-track batches and the seven-case calibration replay have completed
receipts. The narrowband audit still has exactly one usable matched visit; its
saved within-minus-cross sign contrast is 0.0151515. The combined integrity/test
audit is present. Process inspection found no running Python recovery or timeout
job for this investigation, so there is no live analysis to wait on or restart.

The hypothesis register and combined report contain unresolved inference limits,
not a missing result from a launched experiment. No newly supported field mapping
or identity-discriminating test emerged from this review. Merely repeating those
completed batches would not address the absence of an RF-to-message mapping or
independent identity evidence. The same constraint therefore persists for a
second consecutive impasse turn. The objective remains incomplete and the app
goal remains active; this audit is not scientific progress or a completion claim.

## Audit 3 — unresolved requirements confirmed

The preceding turn was no progress, not a verified wait. The combined report's
requirement table was re-read and its saved hash verified unchanged, along with
the component-test log. Semantic field interpretation and validated satellite
identification still have no qualifying artifact. The completed correlation
experiments, software-format evidence and quality-control results do not prove
either requirement. No newly justified next experiment has emerged within the
authorized sources, and no unfinished recovery job is supplying missing evidence.

This is the third consecutive turn with the same evidential impasse. Mark the
app goal blocked, not complete. Its full objective is preserved. Resumption
requires a new independent RF mapping/test vector, or a justified discriminating
hypothesis that the existing corpus can actually test. This does not claim no
such evidence could ever exist online or in the recordings. No new collection,
private access, wider scope, or further blind scans are assumed.
