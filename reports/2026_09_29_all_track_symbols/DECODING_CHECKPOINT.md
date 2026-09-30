# Decoding checkpoint: observations improved, message interpretation unresolved

The active objective remains to decode more recorded symbols and determine what
the bits mean, using satellite associations where useful. It is **not complete**.
This checkpoint separates the new observation evidence from the still-missing
message-decoding evidence. It does not claim a new decoding advance.

## Evidence against the objective

| Requirement | Current evidence | Status |
|---|---|---|
| Recover additional recorded observations | Seven additional DS8 tracks pass the longer-excerpt qualification rule; six whole-word observations agree independently across receivers in two further visits | Progress, with bounded coverage |
| Corroborate unknown early symbols | S13 expanded coverage adds four carriers and 79/108 agreeing selected signs; S13 is an existing acquisition, not a new revisit | Progress in coverage, no new field |
| Establish a usable header coding or repetition rule | State-based prediction does not beat the header baseline; the UT copy candidate does not transfer consistently; prior fixed-layout parity/convolutional tests do not establish an encoder | Unresolved |
| Identify message fields | Firmware serializers define software-level PNT/SYSINFO/MAC structures, but no verified mapping from recorded OFDM observations to those serialized bytes exists | Unresolved |
| Establish satellite-specific bit meaning | Conditional labels and limited qualified cross-session pairs do not yield a validated signature; six new paired words are all known-family states | Unresolved |
| Preserve data and uncertainty | New numerical outputs remain ignored; original census and raw corpus are preserved; aliases, failed gates, conditional labels, and controls are recorded | Verified for this work |

## What the latest checks establish

The six strict paired words in `paired-word-check.json` are all recognized by
the known generator on both receivers. None supplies a new word family or a
message boundary. The larger census's accepted near-family deviations were
already retained as unconfirmed deviations, not corrected or interpreted bytes.

The known pattern's state is not a fixed satellite identifier. Conversely,
failure to predict the early header from that state does not prove the header
is independent, encrypted, or any particular protocol message.

The two newly attempted stronger single-receiver DS8 visits fail paired pilot
qualification. Trying their other stored timing-compatible peer candidates
does not rescue them. Their failures are not evidence that all other visits
or decoder models must fail.

The S13 alias correction is material: DS8-F039/1498 and S13 have identical raw
excerpts and candidate parameters. They must never be counted as two passes or
as independent validation. The expanded carrier coverage is the legitimate
increment.

## Remaining interpretation gap

The firmware investigation reaches receive descriptors and software readers,
but hardware/PHY transformations, coding, scrambling, and resource mapping
remain unverified. The candidate 32-input/114-symbol interpretation has no
validated RF generator or placement. The full-band PNT/SYSINFO probes and the
existing parity tests do not bridge that gap.

At this checkpoint, none of the inspected results supplies a justified new
symbol-to-byte hypothesis that can be validated simply by running the same
tests again. More samples of the known family, unrestricted clustering, or
accepting weaker gates would not itself resolve message semantics. A useful
next semantic experiment needs an independently constrained mapping or an
empirical coding relation that predicts unused changing observations. This is
an investigation limit, not proof that no such evidence exists or that the
signal is undecodable.

## Current audit state

The preceding turn made concrete progress by adding six paired known-family
word observations. This turn revalidated the semantic gap; it did not decode a
new field. This is the first current impasse audit after that progress. The
objective remains incomplete, and no completion or blocked-goal update was
issued in this audit. Earlier blocked audits from older research phases must
not be reused to skip the required current audit sequence.

## Supporting reports

- [Additional paired words and their limits](DS8_REPEAT_WORDS.md)
- [Longer DS8 excerpt recovery](DS8_MORE_FRAMES.md)
- [Corrected S13 coverage and alias audit](PAIRED_DS8_RECOVERY.md)
- [State-to-header prediction](HEADER_STATE_TRANSFER.md)
- [Reference copy transfer](REFERENCE_COPY_TRANSFER.md)
- [Peer candidate checks](NEW_DS8_PAIR_CHECKS.md)
- [Conditional satellite-repeat audit](SATELLITE_REPEAT_AUDIT.md)
- [Firmware/header investigation](../../docs/research/starlink-literature/firmware-header-analysis.md)
- [Full-band software-message probes](../2026_09_28_sequence_semantics/FULLBAND_CONTROL_MESSAGES.md)
- [Header rank and coding tests](../2026_09_28_sequence_semantics/HEADER_BLOCK_RANK.md)

No new RF collection, downloads, commits, deployments, or decoder changes were
performed in this checkpoint review.

### Second current impasse audit

Re-read the latest firmware prefix finding and its saved instruction audit,
`firmware_gmh_sequence_flags.json`. Software prefix bits 4–5 receive a two-bit
value associated with PDU sequence-map handling; value 2 also occurs on the
mismatch path. The audit explicitly supplies neither a complete caller
reachability proof nor RF bit offsets. Therefore it cannot be applied directly
to positions 4–5 in the observed signs or interpreted as a satellite/time field.

Also inspected the saved `fullband_rlc_control_probe.json` scope: it tests a
conditional single-SDU, contiguous 8/20-bit RLC header plus length and control
message under direct real-sign serialization. It supplies no FEC or deinterleaving
solution. The latest prefix association does not establish the missing
transformation or justify rerunning that scan with a new semantic label.

The preceding checkpoint turn produced no new decoding evidence; this turn
revalidated the same semantic blocker. No justified new symbol-to-byte experiment
emerged from these saved leads. This is the second consecutive current impasse
audit. The objective remains incomplete and no blocked-goal update was issued
yet. No tests were rerun merely to restate unchanged results.

### Third current impasse audit: blocked, not complete

Revalidated the saved peer-candidate, strict paired-word, state-to-header, and
reference-copy results. The bounded recovery processes have already returned
terminal success; no pending computation is expected to supply a new mapping.
The six paired words remain known-family observations, and none of the header
or firmware constraints inspected in the three audits establishes decoding into
message bytes.

The same gap has persisted through three consecutive current audits without a
new independently constrained experiment. The goal is therefore marked blocked,
not complete. This is not a claim that every possible reverse-engineering method
has been exhausted. Resuming semantic work needs new discriminating evidence:
for example, a concrete PHY coding/interleaving specification, a verified
symbol-to-byte test vector, or a coding relation that predicts unused changing
bits. Additional observations of the known family alone do not fill that gap.

All earlier recovery results and uncertainties remain available. No new test
run, RF collection, download, commit, deployment, or completion claim accompanies
this status update.
