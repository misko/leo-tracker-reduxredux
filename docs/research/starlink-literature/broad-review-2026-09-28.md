# Starlink literature: expanded technical review, 2026-09-28

## Scope and how to read this review

This expands the [waveform review](review.md), rather than replacing it. It
covers waveform/PNT, receiver engineering, satellite association, Internet
measurement, Direct-to-Cell, terminal security, astronomy, and environmental
effects. The [source index](source-index-2026-09-28.md) supplies full titles,
authors, source links, reviewed versions, and local PDF links. The
[download manifest](downloads-2026-09-28.json) records successful downloads,
hashes, and failed attempts. [Search notes](search-notes-2026-09-28.md) describe
coverage and remaining gaps.

This is a broad technical scoping review, **not an exhaustive inventory of all
Starlink publications or news**. Papers were screened through their abstracts,
methods/results relevant to this project, and conclusions where accessible;
their experiments and mathematics were not independently reproduced. Entries
explicitly marked **abstract/page only** have less evidential coverage. A
downloaded PDF does not imply an equation-by-equation audit. Extracted text is
archived for searching; text extraction can omit graphical content.

## Main findings and implications for this repository

1. **Known waveform structure is the firmest starting point.** P01 establishes
   Ku numerology and synchronization; P05 extends it with pilots, templates,
   and low-entropy T-code structure. X01 and X33 explain how additional OFDM
   resources can improve estimation. None of these imply recovered user packets
   or an authenticated spacecraft identifier.
2. **Estimator precision and navigation accuracy are different.** P03/P05,
   X05, X32, and X38 expose transmitter-clock, beam, ephemeris, and correction
   dependencies. X04 shows substantially different navigation errors for
   different orbit products on the same flight. Better Doppler residuals alone
   cannot validate position or satellite association.
3. **Fifteen seconds is a useful scheduling scale, not a universal continuity
   guarantee.** X06 and X36 connect network changes to reconfiguration; X10
   finds additional switching under mobility and obstructions. Segmentation
   should follow observed discontinuities rather than impose uninterrupted
   phase or a compulsory handover on every boundary.
4. **Observed geometry differs from an ideal constellation.** X14 documents
   deployment and orbital changes. X39 uses directional information with
   specific calibrated antenna hardware; P07 uses a synchronized array.
   Neither validates our directional model without local checks.
5. **Different evidence types must stay separate.** Packet latency (X06–X12),
   terminal uplink leakage (A06–A08), VHF telemetry (existing R03/R04), D2C LTE
   (X15), and Ku synchronization are different observables. X20's local-RFI
   finding is a particularly useful warning against automatic attribution.
6. **Published environmental findings have different levels of directness.**
   Telescope measurements establish radio/optical interference in specific
   conditions. Collision and atmospheric studies also use projections. A
   modeled future ozone hazard is not a measurement of present Starlink-only
   ozone depletion.

The practical reading order for existing-corpus work is **P01 → P05 → X01 →
P03/X05 → X31 → X32/X38 → P07/X39**, followed by X10/X36 for scheduling and
X20 for attribution controls. This is a research recommendation, not a change
to qualified scientific claims or golden fixtures.

## Waveform, estimation, navigation, and receiver engineering

### Existing P01–P07 and R03–R04

Retain the existing [individual reviews](review.md): Humphreys et al.'s signal
structure; Komodromos et al.'s simulator; Qin et al.'s timing; Kozhaya et al.'s
PNT beacon analysis; Qin et al.'s 2026 pilots; joint tracking/beacon refinement;
and StarLoc. The [identity review](identity-timing-orbit.md) covers Kenny's
VHF telemetry notes. These were already in the archive; their PDFs were not
downloaded again. P05's preprint and journal article are versions of one work,
not independent confirmations.

### X01 — Full-frame maximum-likelihood TOA and Doppler

**Qin, Komodromos, Morgan, Humphreys; PLANS 2025.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_ML_Precise_TOA_PLANS.pdf).
Uses live Starlink frames to compare pilot-based correlation, pilot-only ML,
and full-frame estimation with unknown data. Reported post-fit Doppler residual
RMSE decreases from 1469.20/752.43 Hz to 6.34 Hz; TOA improves less. The abstract's
order-of-magnitude wording does not equal the exact ratios of those RMSEs, so
retain the measured values rather than repeat its headline gain literally.
Useful for residual-CFO and decision-directed experiments. Post-fit residual
RMSE is not an independently calibrated frequency truth or position accuracy.

### X02 — Acquisition, Doppler tracking, and positioning: first results

**Neinavaie, Khalife, Kassas; online 2021, journal issue 2022.**
[DOI](https://doi.org/10.1109/TAES.2021.3127488).
Develops GLR acquisition and Kalman-based Doppler tracking of unknown recurring
Starlink signals. A six-satellite experiment reports 10 m horizontal error.
This is foundational evidence for opportunistic Doppler navigation and blind
beacon estimation, not a present-day guarantee about beacon strength, available
signals, or error distributions. Its assumptions about periodicity and orbit
knowledge need checking against the current recording and waveform generation.

### X03 — Exploiting Starlink signals for navigation: first results

**Neinavaie, Khalife, Kassas; ION GNSS+ 2021.**
[Source](https://people.engineering.osu.edu/media/document/2022-10-12/kassas_exploiting_starlink_signals_for_navigation_first_results.pdf).
The conference treatment develops GLR beacon estimation and chirp-parameter
Doppler tracking, with a six-satellite positioning demonstration. It reports
10 m horizontal error and illustrates 22.9 m 3-D error. Read alongside X02 as
closely related early work, not another independent replication. Particularly
useful for comparing which unknown-signal assumptions precede later explicit
PSS/SSS and pilot models.

### X04 — UAV navigation with Starlink

**Hayek, Saroufim, Kozhaya, Kassas; ION ITM 2026.**
[Source](https://people.engineering.osu.edu/media/document/2026-02-11/kassas_uav_navigation_with_starlink.pdf).
Fuses nine satellites' Doppler with IMU and altimeter data over a 500 m,
75-second flight. Reported 3-D RMSE is 102 m with GP/SGP4, 22.1 m with SupGP,
15.57 m with SpaceX ephemerides, and 8.52 m with reference-receiver ephemerides.
The reference-aided final error is 6.13 m. This is a strong example of orbit
quality controlling the result; it is not standalone unaided Starlink navigation.
Use the comparison when evaluating whether an orbit correction actually helps
on held-out recordings.

### X05 — Short-term frame-clock stability

**Qin, Komodromos, Humphreys; 2024 conference work.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/Qin_analysis_of_short_term_time_stability_starlink_frame_clock.pdf).
Extracts frame timing, studies Allan deviation and detrended jitter, and finds
near-discontinuous one-second adjustments plus occasional oscillations and
excursions. Nominal short-term clock quality is promising, but abnormal
intervals undermine naive pseudorange use. This is a predecessor to P03, so
do not double-count it as independent confirmation or generalize its correction
cadence to every satellite generation.

### X31 — LEONARD real-time software receiver

**Morrison, Humphreys; ION GNSS+ 2025.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/morrison_rtsdr_LEOPNT_2.pdf).
Describes adapting a general-purpose software receiver to broadband LEO
signals and presents preliminary Starlink tracking. Discusses nonbinary local
replicas, intermittent frames, and repeated acquisition as engineering costs.
Relevant to keeping acquisition/tracking computationally bounded. This is
receiver-development evidence, not a complete operational global PNT service
or a benchmark for our ARM hardware. Its description of unknown frame content
predates P05's fuller template characterization.

### X32 — Mock implementation of fused LEO GNSS

**Morgan et al.; PLANS 2025.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/morgan_MockStarlink_plans.pdf).
Builds beam-specific clock/orbit models and distributes them as if an operator
provided a cooperative PNT service. Live Starlink observables yield roughly
10-metre-level positioning/timing performance with that support. The central
contribution is making correction requirements explicit. It neither establishes
that SpaceX sells such a service nor demonstrates comparable accuracy using
only uncorrected TLEs and arbitrary standalone recordings.

### X33 — OFDM positioning with unknown data

**Graff, Humphreys; 2025 journal work, author copy.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/ofdm_based_positioning_unkown_data_payloads_graff.pdf).
Derives a Ziv–Zakai TOA bound incorporating known pilots, unknown payloads,
and unknown carrier phase. Comparisons with Cramér–Rao bounds and ML/decision-
directed estimators explain low-SNR threshold effects. Uses simulated LEO
channels to assess accuracy. This supplies estimator theory and experiment
design guidance, not a measurement of our Starlink corpus or a guarantee that
hard symbol decisions are reliable at acquisition threshold.

### X34 — Agile portable antenna for LEO PNT

**Qin, Komodromos, Humphreys; ION GNSS+ 2023.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_agile_antenna.pdf).
An articulated horn switches between satellites in under a second and supports
matched-filter acquisition and beam/channel occupancy measurements. The
reported observations include up to three satellites transmitting assigned
beams toward a service cell. Useful for understanding antenna selection and
observability. It is a particular directional receiving experiment, not proof
that all visible satellites illuminate every receiver or that passive
omnidirectional reception has the same performance.

### X35 — Fused low-Earth-orbit GNSS concept

**Iannucci, Humphreys; 2022 author copy.**
[Source](https://radionavlab.ae.utexas.edu/wp-content/uploads/2022/08/fused_leo_conops.pdf).
Proposes operator-cooperative PNT using a broadband constellation's existing
hardware and quantifies communications opportunity cost. Its modeled allocation
is below 1.6% of downlink capacity under the studied Starlink configuration.
Read as architecture and resource-budget analysis, not a deployed capability
or a contemporary capacity measurement. It clarifies why cooperative clock,
orbit, and resource information changes the problem substantially.

### X38 — Resolving ephemeris and timing errors

**Kassas, Saroufim, Hayek, Kozhaya, Barrett; PLANS 2025.**
[Source](https://people.engineering.osu.edu/media/document/2025-05-19/kassas_towards_navigation_with_non_cooperative_leo_satellites_resolving_ephemeris_and_timing_errors.pdf).
Compares six frameworks, including open-loop propagation, differential
corrections, simultaneous tracking/navigation, and equivalent timing error
compensation. Experiments span multiple LEO constellations and platforms.
In one mixed-constellation vehicle experiment, 3-D RMSE falls from 41.3 m
open-loop to 6.8 m with differential STAN. Results depend on correction links,
initialization, sensors, and geometry. They should not be relabeled as
Starlink-only accuracy or treated as independent of those aids.

### X39 — Direction-of-arrival plus Doppler

**El-Kouba, Kozhaya, Kassas; ION GNSS+ 2025.**
[Source](https://people.engineering.osu.edu/media/document/2025-09-26/kassas_direction_of_arrival_and_doppler_based_positioning_with_starlink_and_oneweb_leo_satellites.pdf).
Uses power-based DOA measurements from electronically steered holographic
antennas and compares DOA-only, Doppler-only, and joint UKF positioning.
Four Starlink and four OneWeb satellites support the experiment and
initialization Monte Carlo study. DOA-only can outperform fusion in the
reported results; additional observables do not automatically improve a
misspecified or differently sensitive estimator. Antenna calibration and
ephemeris assumptions matter when applying this to our directional evidence.

## Internet performance, scheduling, architecture, and Direct-to-Cell

### X06 — A multifaceted look at Starlink performance

**Mohan et al.; 2023 preprint, 2024 revision.**
[Source](https://arxiv.org/abs/2310.09242).
Combines 19.2 million M-Lab speed tests across 34 countries, application tests,
RIPE Atlas measurements, and controlled terminal experiments. Shows regional
variation and synchronized 15-second reconfiguration effects on latency and
throughput. An important bridge between global crowd measurements and local
causal probes. Crowd sampling and deployment date limit generalization; an
end-to-end delay change is not by itself evidence of a particular RF emitter.

### X07 — End-user network characteristics

**Ma et al.; 2022 preprint.**
[Source](https://arxiv.org/abs/2212.13697).
Early terminal measurements cover throughput, latency, outages, environmental
conditions, power, and portability, including remote locations. Documents
substantial variability and limitations of the then-used bent-pipe architecture.
Useful historical baseline. Do not transfer its routing conclusions unchanged
to later inter-satellite-link deployments or infer a universal weather penalty
from a limited end-user sample.

### X08 — Large-scale IPv6 measurement

**Wang et al.; 2024 preprint, January 2026 v3.**
[Source](https://arxiv.org/abs/2412.18243).
Maps reachable Starlink routers, address assignment, and backbone topology.
The reviewed version reports about 5.98 million IPv6 addresses, 49 PoPs, and
98 inter-PoP links. These are version-specific observations, not counts of
unique subscribers or satellites. Useful for network topology context and
understanding outside-in measurement bias. No probing or scans were performed
for this literature review.

### X09 — Democratizing measurement / HitchHiking

**Izhikevich et al.; 2023 preprint, reviewed v2.**
[Source](https://arxiv.org/abs/2306.07469).
Uses Internet-exposed services behind LEO connections to infer latency and
architecture without deploying dishes everywhere. Studies over 2,400 users
in 13 countries and highlights routing-related latency variation. Useful
evidence that low satellite altitude does not uniquely determine Internet RTT.
Service visibility, user sampling, and inferred routing constrain the result;
it supplies network measurements, not IQ or direct signal identification.

### X10 — Vehicular mobility and dynamic beam switching

**Zhao et al.; 2026.** [Source](https://arxiv.org/abs/2601.13790).
Combines terminal diagnostic information, motion/obstruction context, and
satellite identification to study mobile performance. Finds additional beam
switching attempts when visibility or signal quality degrades, beyond the
regular 15-second schedule. Particularly relevant when assessing track
continuity. Its terminal-assisted identification method is not an identifier
decoded from arbitrary passive Ku-band recordings.

### X11 — Starlink, OneWeb, and terrestrial-network reliability

**Ramírez-Arroyo, Peñaherrera-Pulla, Mogensen; 2025 preprint, 2026 revision.**
[Source](https://arxiv.org/abs/2512.19639).
Compares satellite and terrestrial networks in urban, suburban, and forest
settings, then evaluates connectivity diversity. In studied urban cases,
combining Starlink and OneWeb reduces approximately 12–21% individual outage
rates to about 2%. Useful evidence for complementary coverage. This is a
scenario-dependent measurement result, not a universal availability service
level; correlated obstruction and shared failure modes still matter.

### X12 — Horizon global performance prediction

**Benghe, Graure, Shreedhar, Mohan; 2026.**
[Source](https://spearlab.nl/papers/2026/sigmetrics26-horizon.pdf).
Combines 11 months of crowdsourced measurements across over 90 countries with
weather and orbital features. Reports held-out-week mean absolute errors of
17.76 ms latency and 25.63 Mbps throughput. Geographic features dominate its
models. A useful example of temporal and geographic validation, but feature
importance is not a causal decomposition of RF impairments; the model cannot
identify a satellite from a measured waveform.

### X13 — Hypatia

**Kassing et al.; IMC 2020.**
[Source](https://bdebopam.github.io/papers/imc2020-hypatia.pdf).
Provides a simulator and visualization framework for moving LEO network
topologies, including routing, congestion, delay, and link utilization. Valuable
for testing hypotheses under explicitly specified constellations. Its public
design assumptions describe simulated systems, not reverse-engineered current
Starlink scheduling. Pair with X14 and empirical network papers before
interpreting simulation output as deployment behavior.

### X14 — Actual constellation deployment and dynamics

**Ali, Upadhyay, McCormick, Hill, Zhang; 2026 preprint.**
[Source](https://arxiv.org/abs/2603.25835).
Analyzes observation data from 2019–2025 and contrasts real deployment with
static uniform-shell models. Describes shell evolution, altitude changes,
relocations, and clustered satellites interpreted as backups. Useful for
selecting time-correct orbital context and challenging idealized geometry.
Operational intent and failure/lifetime estimates are inferred from public
observations; they are not onboard status telemetry or a future reliability
guarantee.

### X15 — Direct-to-Cell crowdsourced radio measurements

**Garcia-Cabeza et al.; 2025, reviewed v8.**
[Source](https://arxiv.org/abs/2506.00283).
Studies US smartphone measurements from October 2024–July 2025, mostly the
SMS-era service, using cell identifiers and radio metrics. Relates measured
coverage to deployment and estimates possible data capacity from SINR.
Distinguish those capacity estimates from measured application throughput.
This is LTE Direct-to-Cell evidence: its carrier frequencies, modulation,
identity fields, and access procedures do not specify the Ku-band user link.

### X29 — Dissecting satellite-network operators

**Raman, Varvello, Chang, Sastry, Zaki; CoNEXT 2023. Abstract/page only.**
[Source](https://arxiv.org/abs/2310.15808).
Identifies satellite-provider measurements in M-Lab/RIPE data for up to 18
operators, then uses recruited testers to compare web/video performance on
Starlink, HughesNet, and ViaSat. Useful comparative context beyond Starlink.
The PDF could not be retrieved successfully, so this entry does not audit
the numerical results or experimental controls.

### X36 — Making sense of scheduling

**Tanveer, Puchol, Singh, Bianchi, Nithyanand; CoNEXT Companion 2023.**
[Source](https://par.nsf.gov/servlets/purl/10568751).
High-frequency measurements support a hierarchical scheduling interpretation:
satellite allocation to terminals and scheduling of flows. Develops a
terminal/satellite assignment method and an approximate scheduler model.
Useful for forming occupancy hypotheses. An inferred approximation from
terminal observations is not access to the operator's scheduler or a general
passive spacecraft-ID decoder; deployment evolution and mobility matter.

### X40 — Queuing and flow dynamics

**Cech, Mohan, Ott; SIGCOMM 2026. Abstract/author page only.**
[Source](https://github.com/hendrikcech/sigcomm26-dissecting-starlink),
[DOI](https://doi.org/10.1145/3789240.3829162).
Reports controlled per-packet measurements suggesting head-drop queues,
demand-driven rate increases, flow interactions, and resets associated with
15-second reconfiguration. Adds a queueing explanation for some apparent
network variability. The institutional PDF returned HTTP 403; numerical
mechanisms are author-reported and were not audited against the full paper.
Its large network dataset was cataloged but not downloaded.

## Terminal security and firsthand technical articles

### X16 — Black-box terminal security evaluation

**Lennert Wouters; Black Hat USA 2022 slides.**
[Source](https://i.blackhat.com/USA-22/Wednesday/US-22-Wouters-Glitched-On-Earth.pdf).
Documents terminal hardware, boot-chain analysis, and a physical fault-injection
demonstration bypassing signature verification on the evaluated hardware.
Relevant to assessing what firmware reverse engineering can reveal and which
claims require physical access. It is not a remote takeover of the
constellation, a user-traffic decryption demonstration, or proof that later
terminal revisions have identical weaknesses. Slide graphics are only
partially represented in the archived text extraction.

### A01–A04 — Uplink waveform analysis series

**Jiao Xianjun; June 2026, firsthand posts.**
[Demodulation](https://sdr-x.github.io/starlink3/),
[OFDMA/resource allocation](https://sdr-x.github.io/starlink4/),
[modulation/repetition](https://sdr-x.github.io/starlink5/),
[pilots/patents](https://sdr-x.github.io/starlink6/).
A01 demonstrates symbol recovery; A02 investigates allocations across the
OFDM grid; A03 examines constellations and recurring bits; A04 connects pilot
observations with modem patents and analysis methods. Together they complement
the downlink papers with terminal-side measurements. Keep observed symbols
separate from inferred field meanings, and do not substitute their uplink
numerology for P01/P05's downlink numerology. HTML snapshots are saved; these
are technical articles rather than journal PDFs.

### A05 — Modulation, coding, and bit processing

**Jiao Xianjun; July 2026.**
[Source](https://sdr-x.github.io/starlink-supplement7/).
Interprets modem design and patents to explain possible coding and bit-level
processing. Useful for constructing testable deinterleaving/FEC hypotheses.
It does not by itself establish a complete working RF-to-packet decoder or
the semantics of the unencrypted-looking downlink header. Compare with the
existing [firmware leads](firmware-leads.md) before promoting a patent-based
mapping into a measured claim.

### A06 — Rapid channel-occupancy measurements

**Jiao Xianjun; August 15, 2026.**
[Source](https://sdr-x.github.io/starlink-UL-channel-switch/).
Uses AD9361 frequency hopping to scan eight uplink channels, reporting a
100-microsecond dwell and 800-microsecond scan cycle. Produces compact
occupancy evidence instead of a continuous full-band IQ recording. Useful
measurement-design context, but a swept receiver has gaps and channel
switching is not itself a proven satellite handover. The title's 10,000 hops/s
describes receiver scanning, not an established Starlink hopping rate.

### A07 — Cold-start emission behavior

**Jiao Xianjun; August 28, 2026.**
[Source](https://sdr-x.github.io/starlink-UL-cold-start/).
Reports a repeatable terminal-startup sequence with uplink channel scanning
around 24 seconds after power-on. Useful for recognizing terminal-generated
transients and distinguishing initialization from sustained communication.
Treat proposed RF-calibration explanations as hypotheses. Startup behavior
on the tested terminal/firmware is not a constellation-wide timing contract.

### A08 — Deep-cold-start drifting leakage

**Jiao Xianjun; September 26, 2026.**
[Source](https://sdr-x.github.io/deep-cold-start-ul-leak/).
Reports a drifting uplink-region emission after a terminal was powered off for
days, seen in two experiments with two SDRs. Its cause remains unresolved.
The downconverted display frequency must not be mistaken for its RF frequency.
Useful as a concrete counterexample to identifying every drifting feature as
satellite Doppler; these observations alone do not prove a unique hardware
mechanism or a generally available beacon.

### A09 — Budget narrowband beacon reception

**Derek; historical firsthand receiving article.**
[Source](https://sgcderek.github.io/blog/starlink-beacons.html).
Describes LNB/SDR observations of narrowband Starlink-associated signals near
11.325 GHz and their changing frequency. Practical historical context for
front-end setup and Doppler visualization. Already reviewed as R02; this pass
adds an explicit article snapshot. Current tone availability and emitter
identity still require independent evidence.

### A10 — LENS measurement dataset documentation

**Zhao and collaborators; MMSys 2024 project, updated documentation.**
[Source](https://github.com/clarkzjw/LENS).
Documents a geographically distributed Starlink network-measurement dataset,
terminal configurations, service tiers, obstruction context, and collection
changes. Useful for reproducing network-performance research and tracking
measurement provenance. It is packet/terminal telemetry, not broadband raw
IQ. Only the documentation snapshot was downloaded; coverage varies over time.

## Radio astronomy and attribution

### X17 — First-generation LOFAR unintended radiation

**Di Vruno et al.; A&A 2023. Abstract/publisher page only.**
[Source](https://www.aanda.org/articles/aa/full_html/2023/08/aa46374-23/aa46374-23.html).
Reports satellite-correlated emission between 110 and 188 MHz and distinguishes
observed emission from constellation-level interference simulations. Foundational
evidence that a communications spacecraft can radiate outside its intended
communication bands. This is not a Ku-band demodulation result. Both attempted
PDF routes failed, so the quantitative methodology was not audited locally.

### X18 — Second-generation LOFAR radiation

**Bassa et al.; A&A 2024.** [Source](https://arxiv.org/abs/2409.11767).
Measures broadband radiation from v2-Mini and D2C satellites in low-frequency
bands and compares range-corrected brightness with earlier generations.
Some measured emissions are up to 32 times stronger. Important evidence that
generation matters and that intended-carrier frequency is not the whole
interference story. Brightness varies with satellite and band; this maximum
ratio should not be applied to every spacecraft or frequency.

### X19 — EDA2/SKA-Low survey

**Grigg et al.; A&A 2025. Abstract/publisher material only.**
[Source](https://arxiv.org/abs/2506.02831).
Analyzes roughly 76 million sky images over about 29 observing days, reporting
112,534 detections from 1,806 Starlink satellites. Extends the evidence beyond
small targeted samples across the SKA-Low range. Counts refer to detections,
not that many distinct emitters or simultaneously active beams. Available
PDF endpoints failed here; observational selection and calibration details
need full-text review before reusing quantitative thresholds.

### X20 — 21CMA search and local-RFI counterexample

**Yang et al.; March 2026 preprint. Abstract only.**
[Source](https://arxiv.org/abs/2603.07631).
Develops TLE-guided observing and detection with limited single-pod sensitivity.
Does not detect the sought broadband Starlink radiation; validates transit
identification using decoded ORBCOMM IDs and attributes impulsive broadband
bursts to nearby power-line arcing. Especially relevant to negative controls
and false-attribution risk. Non-detection is sensitivity-limited, not evidence
that the positive LOFAR/EDA2 results are false. The PDF transfer was truncated.

### X41 — SNIFFLES, 1–26 GHz

**Indermuehle, Lourenço; MNRAS 2026, archived journal PDF via arXiv.**
[Source](https://arxiv.org/abs/2608.12999).
Reports 4,629 satellite-tracked observations across four constellations with
Mopra and ATCA follow-up. Separates intended transmissions, unwanted emissions
(including harmonics), and unintended platform radiation, with Doppler/orbit
checks for attribution. Useful for distinguishing signal classes and combining
spectral evidence with geometry. The aggregate detection totals cover several
constellations; they must not all be attributed to Starlink or interpreted as
user-link waveform structure.

### X42 — D2C radiation and illumination dependence

**Dong, Wang, Cai, Akan; May 2026 preprint. Abstract only.**
[Source](https://arxiv.org/abs/2605.17150).
Reanalyzes the EDA2 detection corpus by spacecraft type, finding different
sunlit/eclipsed behavior for D2C and comparison satellites, plus localized
spectral/polarization effects. Proposes mechanism-discrimination tests.
This is reuse of X19's observations, not a new independent observing campaign.
The proposed thermal/electronic explanation remains an interpretation; the
PDF could not be retrieved, and the summary follows the indexed preprint.

## Optical astronomy, environment, and operational context

### X21 — LEO population and Starlink impact

**Jonathan McDowell; ApJL 2020. Abstract only.**
[Source](https://arxiv.org/abs/2003.07446).
Models how the proposed Starlink population would change the density and
visibility of satellites at low altitudes, including latitude dependence.
A foundational geometry-based impact analysis. Its proposed constellation
is a historical scenario rather than a September 2026 satellite census;
predicted visible-satellite density is not the same as measured science loss.
The attempted PDF transfers were incomplete or rejected.

### X22 — Rubin/LSST brightness and trail mitigation

**Tyson et al.; AJ 2020, reviewed arXiv v3.**
[Source](https://arxiv.org/abs/2006.12417).
Combines sensor tests, optical observations, and mitigation analysis. Darkening
reduces artifacts, but trails persist and can introduce systematic errors even
when saturation is avoided. Includes avoidance, masking, and image correction
tradeoffs. This is instrument-specific evidence and modeling, not proof that
all optical surveys are equally affected or that a brightness target removes
every astronomical consequence.

### X23 — Observed ZTF impact

**Mróz et al.; 2022.** [Source](https://arxiv.org/abs/2201.05343).
Finds 5,301 Starlink-associated streaks in 2019–2021 ZTF data and a rise in
affected twilight images from under 0.5% to 18%. Reports mitigation from
visors and distinguishes detected streaks from then-current scientific impact,
which was not yet severe for ZTF operations. Its future-constellation
extrapolation should not be presented as an observed outcome or transferred
unchanged to Rubin.

### X24 — D2C optical brightness in mitigation mode

**Mallama, Cole, Respler, Harrington; 2025.**
[Source](https://arxiv.org/abs/2502.03651).
Uses observations after brightness-mitigation attitude changes and compares
apparent brightness with distance-normalized values. Reports mean apparent
magnitude 5.16 and a 1,000-km-normalized mean of 6.47 for its sample.
Illustrates the need to control range, attitude, phase angle, and observing
date. These optical magnitudes do not measure radio-emission strength or
establish that mitigation meets every telescope's requirements.

### X25 — Megaconstellation risks

**Boley, Byers; Scientific Reports 2021.**
[Source](https://www.nature.com/articles/s41598-021-89909-7).
Connects congestion/collision exposure, reentry material, astronomy, and
governance using simple quantitative models and deployment scenarios.
Useful for framing cumulative effects that single-spacecraft analyses miss.
Its collision and atmospheric projections are conditional, not records of
predicted collisions actually occurring or a validated current atmospheric
chemistry budget.

### X26 — Aluminum oxidation and ozone-depletion potential

**Ferreira, Huang, Nomura, Wang; GRL 2024.**
[DOI](https://doi.org/10.1029/2024GL109280).
Molecular-dynamics modeling estimates aluminum-oxide production during reentry;
a modeled 250-kg satellite produces roughly 30 kg of oxide nanoparticles.
Links accumulation scenarios to possible ozone chemistry consequences. This
does not directly measure global ozone loss caused by Starlink. The saved
26-page PDF is a printout of the article in a public FAA docket, not the
publisher's typeset PDF; its provenance is explicit in the index.

### X27 — May 2024 storm and orbital decay

**Ashruf et al.; 2024 preprint, June 2025 v2.**
[Source](https://arxiv.org/abs/2410.16254).
Studies TLE-derived decay of 12 Starlink satellites around the May 2024 storm
and an earlier enhanced-decay period. Relates the evolution to space-weather
and density changes. Useful context for time-varying propagation uncertainty.
The mechanisms are interpretations of public orbital/environmental data,
not onboard drag or maneuver telemetry; do not attribute every residual to
space weather.

### X28 — Solar source of the February 2022 loss event

**Gopalswamy, Xie, Yashiro, Akiyama; 2023 preprint.**
[Source](https://arxiv.org/abs/2303.02330).
Connects a solar eruption, magnetic-cloud evolution, and geomagnetic conditions
to the storm accompanying Starlink losses. Demonstrates that apparently
moderate geomagnetic activity can matter at low deployment altitudes. It is
event-specific solar/space-weather analysis. The paper itself uses differing
loss counts in its abstract/introduction; this review avoids treating one
count as a verified fleet inventory.

### X30 — Operator brightness-mitigation guidance

**SpaceX; operator technical report, archived copy.**
[Source](https://api.starlink.com/public-files/BrightnessMitigationBestPracticesSatelliteOperators.pdf).
Describes approaches involving materials, spacecraft geometry, and attitude
to reduce reflected sunlight. Useful primary evidence of the operator's design
intent and engineering constraints. It is not an independent measurement of
effectiveness; compare with X22–X24. The archived file's digest identifies the
copy because the public URL is not a stable publication-version identifier.

### X37 — Starlink progress report 2024

**SpaceX; year-end operator report.**
[Source](https://www.starlink.com/public-files/starlinkProgressReport_2024.pdf).
Describes deployment, hardware/service development, connectivity applications,
and safety/sustainability activity for the reporting period. Useful for
operator terminology, engineering context, and locating claims requiring
independent evaluation. This is a historical operator account, not a current
fleet census, an audited performance comparison, or the latest comprehensive
regulatory record. Its statistics should retain the 2024 reporting date.

## Unresolved questions worth carrying forward

- Which downlink header fields have independently demonstrated semantics,
  beyond low-entropy or repeatable structure?
- How much of the P05 predictable structure is usable within our actual
  bandwidth, oscillator stability, and short recorded intervals?
- Can orbit/clock/beam effects be separated using frozen parameters and
  genuinely held-out passes, rather than fitted away on the same data?
- Which modern-generation tones and pilot patterns persist across satellites,
  time, pointing, and beam transitions?
- Can a satellite association survive plausible alternative satellites,
  wrong-time controls, local interference, and receiver drift?
- How much of reported network variability comes from RF propagation versus
  scheduling, queues, terrestrial routing, and service-tier policies?

These are proposed research questions. This review made no RF collections,
network scans, runtime changes, or changes to scientific fixtures.
