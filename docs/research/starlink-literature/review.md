# Starlink waveform literature review

## Motivation

Identify the public results most useful for known-pilot, QAM, timing, Doppler,
and satellite-association research on existing recordings.

## Problem

Waveform detection, symbol decisions, communications decoding, and navigation
are different achievements. Results also differ by link, satellite generation,
capture bandwidth, receiver clocks, and observation date.

## Solution

Use the established Ku-band numerology and explicit synchronization/pilot
sequences as references. Treat precise ranging, payload recovery, and emitter
identity as separate problems requiring separate evidence.

## Method

Reviewed 2026-09-27. Sources below are primary research or firsthand author
measurements. Entries summarize findings and limitations, not independent
reproductions. Local PDFs and source snapshots are indexed in `downloads.json`.

## P01 — Signal Structure of the Starlink Ku-Band Downlink

**Humphreys, Iannucci, Komodromos, Graff; 2022 preprint / 2023 publication.**
[Paper](https://arxiv.org/abs/2210.11578).

Foundational reverse engineering: eight 250 MHz slots across 10.7–12.7 GHz,
approximately 240 MHz waveform bandwidth, a 1024-point transform, 32-sample
cyclic prefix, 234.375 kHz spacing, and 4.4 microsecond symbol intervals.
Frames repeat on a 750 Hz grid, with 302 symbol-length intervals and a
4.533 microsecond guard. PSS and SSS sequences are explicitly published;
PSS is a special time-domain sequence. Four central OFDM subcarriers are vacant.
The paper observes 4-QAM and 16-QAM and distinguishes additional end-of-frame
structure. Its frequency convention includes a half-subcarrier offset from
the nominal channel midpoint; reproductions must preserve that convention.

**Use:** acquisition, numerology, FFT/bin mapping, and synchronization replicas.
**Limit:** historical channel occupancy is not a present-day allocation rule;
recovering modulation symbols is not recovering user packets.

## P02 — Signal Simulator for Starlink Ku-Band Downlink

**Komodromos, Qin, Humphreys; ION GNSS+ 2023.**
[Paper](https://radionavlab.ae.utexas.edu/wp-content/uploads/komodromos_starlink_simulator.pdf)
and [author code](https://gitlab.com/radionavlab/public/ut-starlink-signal-simulator).

Provides a simulator for the published signal model, including delay, Doppler,
and noise, and describes acquisition hypothesis testing.

**Use:** controlled experiments and numerical cross-checks.
**Limit:** generated signals are synthetic; the original simulator predates the
2026 pilot/template characterization. Do not equate simulated success with
validation on current satellite emissions.

## P03 — Timing Properties of the Starlink Ku-Band Downlink

**Qin, Graff, Clements, Komodromos, Humphreys; 2025 preprint.**
[Paper](https://arxiv.org/abs/2501.05302).

Measures periods of nanosecond-level frame jitter alongside abrupt timing
corrections, high-jitter intervals, and loose GPS-time discipline. v1.0/v1.5
exhibit approximately once-per-second corrections; v2.0-mini corrections are
smaller and irregular. Scheduling and timing changes occur on 15-second scales.

**Use:** frame-timing and clock-error models; distinguishing receiver-relative
observables from absolute navigation measurements.
**Limit:** precise TOA does not alone establish absolute range. Transmitter
clock corrections, receiver errors, geometry, and association still matter.

## P04 — Unveiling Starlink for PNT

**Kozhaya, Saroufim, Kassas; NAVIGATION 72(1), 2025.**
[DOI](https://doi.org/10.33012/navi.685) and
[author PDF](https://people.engineering.osu.edu/media/document/2025-08-06/kassas_unveiling_starlink_for_pnt.pdf).

Blind estimation reveals recurring OFDM structure extending across the frame,
with nearly 18 dB additional processing gain relative to PSS/SSS alone.
The paper extracts code, carrier, and Doppler observables and studies
communication-related discontinuities and frequency-correction mitigation.

**Use:** recurring-signal estimation and low-SNR acquisition/tracking.
**Limit:** “full OFDM beacon” denotes predictable components across the grid,
not knowledge of all payload symbols. Experimental positioning results depend
on the estimator and correction assumptions; they are not universal accuracy.

## P05 — Pilots and other predictable elements of the Starlink Ku-band downlink

**Qin, Psiaki, Bowman, Humphreys; February 2026 preprint; September 4, 2026 journal article.**
[Journal](https://www.nature.com/articles/s44459-026-00075-6),
[preprint](https://arxiv.org/abs/2602.02627), and
[supplements](https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/qin-starlink-pilots/).

Publishes edge-pilot sequences and a reference template. Post-header QPSK
regions can contain 60-bit T-codes that repeat across frequency and shift by
16 subcarriers between symbols. The corpus covers v1.0, v1.5, and v2.0-mini.
The paper estimates about 48 dB total processing gain under assumptions
including identifying T-code regions and recovering their codes. Its
demodulation framework includes QPSK/4-QAM orientation distinctions, 16-QAM,
and 32-QAM.

**Use:** exact pilot verification, equalization, residual carrier/sample-rate
correction, constellation assessment, and template/T-code experiments.
**Limit:** empty resource allocations as the origin of T-codes are an author
hypothesis. “Decoded frames” are symbol-domain data, not decrypted packets.
48 dB total gain is not directly interchangeable with P04's incremental gain.

## P06 — Joint Tracking and Beacon Refinement of Wideband Starlink LEO Signals for PNT

**Kassas group; 2025 author-hosted paper.**
[Author PDF](https://people.engineering.osu.edu/media/document/2025-09-26/kassas_joint_tracking_and_beacon_refinement_of_wideband_starlink_leo_signals_for_pnt.pdf).

Extends beacon estimation/tracking and discusses Doppler shift and stretch.
Reports reduced narrowband pilot-tone strength after 2023.

**Use:** evaluate tracking models and the limits of older tone-based examples.
**Limit:** this is a targeted review of tracking implications, not a reproduction
of the complete receiver or a verified inventory of all current beacon modes.

## P07 — StarLoc: Pinpointing Transmitting LEO Satellites from a Single Passive Array

**Janveja, Zhang, Sie, Vasisht; MobiSys 2026.**
[Paper](https://arxiv.org/abs/2604.21147) and
[project](https://connectedsystemslab.github.io/starloc/).

Combines three-receiver interferometry with orbital constraints to localize
transmitting satellites. Evaluates transmissions from 81 Starlink satellites;
releases IQ and supporting metadata.

**Use:** Doppler/angle/association experiments with synchronized receivers.
**Limit:** the released 2 MHz captures do not contain a full broadband channel;
the reported angle/range performance does not transfer to our receiver setup.

## R01 — Terminal uplink reverse engineering

**Jiao Xianjun; firsthand technical posts, June 2026.**
[Demodulation](https://sdr-x.github.io/starlink3/),
[OFDMA allocations](https://sdr-x.github.io/starlink4/),
[modulation](https://sdr-x.github.io/starlink5/),
[pilots](https://sdr-x.github.io/starlink6/).

Reports 60 MS/s uplink numerology, 1024-point transforms, a 48-sample prefix,
training fields, and OFDMA allocations from terminal measurements.

**Use:** separate uplink hypotheses and examples of symbol-level analysis.
**Limit:** independent measurement reports, not a complete peer-reviewed
constellation specification. Uplink and downlink numerologies are different.

## R02 — Early narrowband reception

**Derek, firsthand receiving report.**
[Receiving Starlink satellite beacons on a budget](https://sgcderek.github.io/blog/starlink-beacons.html).

Shows LNB/SDR reception of Doppler-shifted narrowband signals around 11.325 GHz.
Useful historical receiving context, not proof of their present availability
or that every drifting tone is a Starlink transmitter.

## Implications and open questions

1. Validate sample-rate conversion, bin indexing, PSS/SSS, and edge pilots
   against a digest-bound real full-channel fixture before expanding claims.
2. Track carrier offset and sample-rate error separately where the model
   requires it. Clean constellations alone do not identify an emitter.
3. Study templates/T-codes as predictable structure; do not assume every
   four-point constellation region is high-entropy communications payload.
4. Distinguish narrowband tones, OFDM sync sequences, and extended recurring
   OFDM structure whenever using the word “beacon.”
5. Public evidence reviewed here is incomplete for all PHY headers, coding
   configurations, higher-layer mappings, and a complete interoperable decoder.
6. These conclusions address Ku-band user links. Direct-to-Cell LTE, gateway
   links, and optical inter-satellite links require separate catalogs.
