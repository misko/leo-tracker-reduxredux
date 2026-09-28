# External Starlink dataset catalog

## Motivation

Find reproducible observations for bounded offline waveform experiments.

## Problem

Bandwidth, duration, data representation, and provenance determine what a
dataset can establish. Large “raw” datasets are not necessarily raw RF IQ.

## Solution

Keep acquired files in `local/data/`, with checksums in `downloads.json`.
Start with UT's small full-channel IQ slice and reference sequences. Catalog
multi-gigabyte datasets without downloading them in this initial collection.

## Method

Catalog established 2026-09-27 from original source documentation. The UT ZIP
was opened and its metadata and file sizes checked. No waveform decoding or
independent satellite identification has been performed as part of cataloging.

## D01 — UT full-channel IQ slice (downloaded)

[Direct ZIP](https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/qin-starlink-pilots/raw-iq-data/exemplar250-257.zip)

- Local directory: `local/data/ut-pilots/`.
- Real received Ku-band IQ; one approximately 240 MHz channel.
- 250 MS/s complex sampling, 50 ms duration, 12,500,000 complex samples.
- Interleaved little-endian signed int16 I,Q; 50,000,000-byte binary.
- JSON center frequency: 12,075,117,197.1668 Hz; channel index 6.
- ZIP size observed: 40,714,282 bytes.
- Related exemplar indices 250–257; metadata declares seven whole frames.
  Do not interpret eight referenced indices as eight complete frames.
- Archive includes metadata and a MATLAB reader/PSD example.
- Timing caveat: `unix_time` is the string `17375117563`, whose units/convention
  are undocumented and inconsistent with ordinary 2025 Unix seconds. Preserve
  it verbatim; do not use it for TLE association without resolving the convention.
- The README refers to `readIQslice.m`, but the reader is a local function inside
  `plotIQpsd.m` in the inspected archive.

Suitable for acquisition, FFT/bin mapping, equalization and pilot/QAM analysis.
It is neither a long Doppler pass nor a simultaneous 2 GHz-band recording.
See the supplementary license for code/data terms; preserve attribution.

## D02 — UT decoded exemplar frames and reference material

[Source directory](https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/qin-starlink-pilots/)

1,009 demodulated frames from STARLINK-31848, v2.0-mini, captured January 21,
2025, according to the author guide. The matrix dimensions are 1024 subcarriers
by 301 OFDM symbols by 1009 frames; PSS is not an OFDM column. Soft/hard
symbol estimates and modulation/timing metadata support comparison.

The roughly 5 GiB decoded MAT file is **cataloged, not downloaded** in the initial
collection. The small reference template, synchronization vectors, MATLAB
generators, guides and licenses are downloaded. These are external numerical
references, not runtime dependencies. MIT code / CC-BY-4.0 data are described
in the supplied guide and license.

## D03 — StarLoc (cataloged; README downloaded)

[Zenodo](https://zenodo.org/records/19043854),
[README](https://zenodo.org/records/19043854/files/starloc_full_dataset_README.md?download=1),
[full dataset on Box](https://uofi.box.com/s/viph8qs4xdleb3nvngjl6yyw77rlakd8).

Three synchronized X310 receive channels, 2 MHz bandwidth at 2 MS/s, centered
on 11.325 GHz. Each observation lasts 900 seconds and includes IMU/GNSS and
contemporaneous TLE data. Zenodo lists a 42.4 GB observation ZIP. Verify binary
type using the author loader before consuming `.dat` files; the README alone
does not establish the sample dtype.

Suitable for partial-band Doppler and interferometry, not complete broadband
symbol recovery. Bulk IQ has not been downloaded here.

## D04 — Direct-to-Cell and laboratory LTE (cataloged only)

[Dataset](https://huggingface.co/datasets/Morty0311/starlink-d2c-x300-duplex-iq).

Uploader-described paired uplink/downlink X300 IQ at 10 MS/s, little-endian
complex float32. Two field captures are 41 and 61 seconds at downlink
1992.5 MHz / uplink 1912.5 MHz; another capture is a laboratory LTE reference.
Approximately 17 GB total. This is a different air interface from Ku-band
broadband Starlink. Field attribution and packet integrity are not independently
validated by this catalog. Check the dataset's custom terms before reuse.

## D05 — Watson monitoring data (cataloged only)

[Zenodo](https://zenodo.org/records/8400658).

March 2023 Altrincham Starlink/OneWeb monitoring, 31.5 GB. Includes HackRF band
scans, 11.325 GHz beacon monitoring, TLEs and plots. A sweep spanning 2 GHz is
not simultaneous 2 GHz IQ. Inspect each file's format before proposing
symbol-domain processing.

## D06 — UT simulator (code reference; not captured data)

[Repository](https://gitlab.com/radionavlab/public/ut-starlink-signal-simulator).

Synthetic waveform functions for delay, Doppler, noise and acquisition studies.
The repository README is saved locally; the simulator is not installed or
introduced as a runtime dependency.

## Exclusions and next experiments

Network latency/throughput datasets such as LENS and WetLinks, dish telemetry,
and astronomical detection CSVs do not substitute for received IQ.

Recommended first work: reproduce full-channel synchronization and edge-pilot
responses on D01 with known-wrong controls, then compare against D02 reference
vectors. Record exact input hashes and processing settings. Acquire a bounded
D03 subset only when a specific Doppler/association experiment needs it.
