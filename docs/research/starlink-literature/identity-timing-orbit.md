# Cleartext, identity, timing, and orbit investigation

## Motivation

Determine which Starlink transmissions can expose readable identification,
timing, or position information, and which quantities require external inference.

## Problem

Ku-band broadband, VHF telemetry, and Direct-to-Cell LTE are different signals.
A common sync sequence is not a spacecraft ID; a receiver TOA is not a broadcast
UTC timestamp; satellite position telemetry is not a receiver position solution.

## Solution

The strongest direct metadata lead is VHF telemetry. Ku-band has a promising
apparently unencrypted header but unresolved field semantics. D2C LTE has
reported spacecraft-number associations through cell identity. Continue
Ku-band analysis on existing recordings; use published VHF packets to develop
and assess the separate telemetry hypothesis without new collection.

## Method

Investigation date: 2026-09-27. Read primary papers, author packet-format
reports, firsthand D2C measurements, and modem patents. Reinterpreted five
87-byte packet examples from Kenny's 2023 PDF with little-endian integer and
IEEE float32 readers. No RF was collected; no new waveform demodulation, CRC
validation, cryptographic authentication, or NORAD association is claimed.

## Evidence matrix

| Signal/source | Readable information | Claim limit |
|---|---|---|
| Ku PSS/SSS and edge pilots | Known sequences; relative frame timing and frequency | Shared sequences do not encode a unique spacecraft ID |
| Ku variable-length header after SSS | Qin reports evidence of unencrypted structure | Semantics of ID, clock, or orbital fields not established |
| Ku T-codes | Low-entropy recurring structure | Not established as IDs or navigation messages |
| VHF beacon | Published spacecraft number, time and position fields | Historical formats; current coverage and integrity need validation |
| D2C LTE cell identity | Reported mapping from eNB part to fleet number | Empirical deployment mapping, not a Ku-band rule or NORAD ID |
| Internet ephemeris publication | Orbit predictions and identifiers | External data, not a decoded RF field |

## Ku-band: the first place to inspect

[Qin et al.](https://www.nature.com/articles/s44459-026-00075-6) identify a
variable-length QPSK header after PSS/SSS. After removing the reference
template, the header has BPSK-valued deviations, long constant runs, and
frame-to-frame repetition. They infer that it is unencrypted but explicitly
do not interpret its contents semantically. This is evidence of accessible
structure, not a completed header decoder.

The earlier [structure paper](https://arxiv.org/abs/2210.11578) conjectured
satellite/channel/modulation scheduling information near the frame start;
that conjecture must not be reported as a recovered spacecraft-ID field.

The [downlink modem patent US12074683B1](https://patents.google.com/patent/US12074683B1/en)
and [uplink patent US12003350B1](https://patents.google.com/patent/US12003350B1/en)
are architecture clues. The latter describes PDU header sequence, partial,
MCS-length and MCS fields. A PDU header is not automatically the same object as
the empirical OFDM frame-header region. Patents describe embodiments, not
proof of the exact current mapping. The
[bit-processing article](https://sdr-x.github.io/starlink-supplement7/)
is a patent interpretation, not a demonstrated complete RF header decoder.

An unencrypted field may still require descrambling, deinterleaving and FEC.
Conversely, low entropy alone does not identify its meaning. A frame counter,
beam identifier, resource assignment, and spacecraft number can share apparent
stability and must be distinguished with independent observations.

## VHF: directly relevant published telemetry

[Kenny's 2023 report](https://www.emitters.space/Starlink.pdf) documents
137.055 MHz LoRa examples with spacecraft number, UTC, coordinates, altitude,
and GPS time fields. The [January 2025 update](https://www.emitters.space/2025%20January%20Starlink%20Update.pdf)
describes multiple packet formats, including an encrypted-message format.
The notes concern telemetry used during early orbital operations; they do not
establish continuous availability from every operational satellite.

Local check: `local/data/vhf-published-packet-check.json` holds five parsed
examples and provenance. Two packets with spacecraft number 2385 have counters
4096174 and 4096175, with reported UTC values 100 seconds apart. This is a
consistency check on published bytes, not independent reception evidence.

Two source-quality findings matter: the first example's latitude bytes yield
approximately -33.559757 degrees, while the table prints -31.559757; and the
2025 table has ID/width inconsistencies. Validate layouts per packet type.
Never assume an internal spacecraft number equals a NORAD catalog number.

The VHF sample cannot be recovered from the UT Ku-band IQ file: the frequencies
were not recorded. Existing published packets allow preliminary format work.

## D2C: a separate identity route

[Pellicer's July 2026 field report](https://www.antenasgsm.com/opendata/articulos/identificamos-satelite-starlink-y-medimos-conexion-direct-to-cell)
reports `eNB = cell_id >> 8` and `sector = cell_id & 255`, with the eNB part
matching STARLINK fleet numbers in the measured session. Example: cell ID
2898201 gives 11321 and sector 25. The author cross-checks orbital visibility
and explicitly avoids claiming a universal permanent rule. This uses the LTE
cell identity, not the small physical cell ID (PCI). Neither is a NORAD number.

The page was reviewed online; a local snapshot attempt returned HTTP 403.
No D2C packet was decoded in this investigation.

## Timing and orbit are different questions

The [Ku timing study](https://arxiv.org/abs/2501.05302) measures clock steps,
jitter and loose GPS-time steering. Precise arrival-time estimates do not
establish a transmitted UTC field or a precise propagation delay. Doppler
also mixes orbital motion with oscillator errors and transmitter corrections.

VHF reported position is a time-tagged spacecraft fix, not automatically a
complete orbit model or a useful navigation broadcast. In our published-packet
check, interpreting GPS time with the applicable 18-second GPS–UTC offset puts
the GPS timestamp 2.2–2.81 seconds before the packet's integer UTC field.
Field age/meaning must be resolved before using it for propagation timing.

For independent comparisons, use time-matched
[CelesTrak supplemental elements](https://celestrak.org/NORAD/elements/supplemental/)
or [Starlink operator ephemerides](https://docs.space-safety.starlink.com/docs/).
Current orbit data cannot validate a 2023/2025 capture without historical data.
SpaceX's documentation distinguishes public ephemeris publication from its
operator-restricted screening API.

## Bounded follow-up using existing data

1. On the UT 50 ms sample, independently acquire PSS/SSS, equalize, and inspect
   post-SSS soft symbols. Use the template to expose header deviations, while
   tracking SNR, phase ambiguity, and sample-rate error. Seven whole frames
   suffice for an initial structure check, not a unique field interpretation.
2. Require consistent decoding, applicable integrity checks, repeated-field
   behavior, and wrong-template controls before naming any candidate field.
   Satellite-ID claims need multiple independently labeled spacecraft; one
   satellite's short sample cannot distinguish ID from a constant configuration.
3. For VHF, work first from published packets and seek a documented archival
   IQ/packet corpus with reception time and integrity metadata. Reproduce
   format-dependent time/coordinate extraction and map internal IDs externally.
4. Keep D2C LTE work separate from Ku-band. Its cell-ID reports are a useful
   external labeling lead, not a shortcut to interpreting Ku headers.

No new RF collection was started. Existing scientific goldens and production
contracts remain unchanged; this is a research finding, not a detector release.
