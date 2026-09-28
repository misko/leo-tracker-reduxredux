# Public firmware leads for waveform decoding

Reviewed 2026-09-28. Scope: public online artifacts only. No private researcher
access, hardware extraction, or new RF collection is assumed. This is a source
review plus inspection of one public Linux-partition binary. No modem executable
has yet been recovered or disassembled in this review.

## Acquisition and binary inspection results

The APK described below corresponds to 2026.16.0, build 2000015367 in
[APKMirror's catalog](https://www.apkmirror.com/apk/space-exploration-technologies-corp/starlink/starlink-2026-16-0-release/).
Direct APKMirror and APKPure requests returned HTTP 403; the indexed APKMirror
download link returned an invalid-nonce page. Uptodown's indexed Starlink pages
returned HTTP 404. TechSpot links onward to Google Play rather than hosting an
independent binary. These attempts did not obtain the APK; they do not establish
that it is unavailable through other public routes.

A different public artifact was successfully downloaded from
[Microsvuln's ECC-remover repository](https://github.com/Microsvuln/starlink-user-terminal-firmware-ecc-remover/tree/712de48bf587ef702d8775e604750c81016e7bda):
`linux_with_ecc.zip`, 16,381,647 bytes, SHA-256
`4159bd3f8e86b2247d900e6561075e7c3cc1685597ada268e2e13b066d0ced6d`.
It contains a 33,554,432-byte partition image. Origin and manufacturer
authenticity are not verified; the repository is a third-party upload.

Local inspection removed the SXECC framing while retaining the first block's
215 payload bytes, then verified the footer's MD5 against the complete payload.
This checks internal consistency, not authenticity. The resulting FIT image is
13,573,316 bytes, SHA-256
`ed48220c654c4c7946a3b6f4f43934efe030e7c178099d8dad3b137bcbd1f2f8`.
Structured FIT parsing recovered a kernel, 25 device trees, and a ramdisk.
LZMA decompression and CPIO inventory yielded 1,281 filesystem entries.
The kernel identifies itself as Linux 5.15.55-rt48-g7039d66996e1, built
2022-11-03; the root filesystem identifies Buildroot 2022.02.2.

The ramdisk contains an empty `sx/local/runtime` directory, runtime setup tools,
and system utilities. It does not contain `phyfw`, `rx_lmac`, or `tx_lmac`.
Therefore this artifact is not the modem runtime needed for header decoding.
No code from the image was executed. The downloaded image, derived files,
inspection script, FIT/CPIO inventories, and hash manifest remain in ignored
`local/firmware/`. No radio fields were decoded by this inspection.

## Concrete acquisition lead

[TitleOS's July 2026 APK investigation](https://blog.titleos.dev/exploring-the-star%28link%29s)
reports `assets/sw_update_catson.sxv` and `assets/sw_update_catapult.sxv` in
`com.starlink.mobile_v2000015367.apk`. Reported APK SHA-256:
`03a295c4681eca133cfec9b1cf58ceddd83dcd8ef1f6e0a5d303dd9f34f1c808`.
The author extracted a roughly 45.8 MB RomFS from the Catson bundle, containing
`bin`, `dat`, and revision information identifying a March 2026 build.
The article describes configuration and embedded firmware files, but does not
establish that the bundle contains a complete radio decoder. Catson/Catapult
refer to processor families, not aviation versus consumer service.

This is an actionable online-only lead, independently unverified here. Locate
the matching public APK, verify its signing certificate and hash/provenance,
inventory its assets, and inspect the extracted files before assuming which
parts of the modem are present. Keep packages and extracted files under ignored
`local/`; record hashes and sizes. Static analysis does not require installing
the app or flashing a terminal.

## What existing reverse engineering supplies

[Quarkslab's investigation](https://blog.quarkslab.com/starlink.html) identifies
`phyfw`, receive/transmit lower-MAC processes, and runtime message schemas.
These identify promising analysis targets. Its emulator could not operate the
hardware-dependent PHY and lower-MAC processes. Its published Slate structures
describe internal process communications; they are not established Ku-band
over-the-air header layouts. Storage ECC is likewise not the radio channel code.

[Quarkslab's repository](https://github.com/quarkslab/starlink-tools) supplies
extraction and analysis tools but explicitly excludes the firmware itself.
[SpaceX's Wi-Fi router release](https://github.com/SpaceExplorationTechnologies/starlink-wifi-gen2)
is router code, not a published satellite modem implementation.

## Proposed static analysis and validation

1. Identify executable architectures and embedded firmware; distinguish scripts,
   configuration, executable code, and hardware-loader blobs.
2. Inspect PHY and receive-MAC code, if present, for header parsing, bit masks,
   field widths, CRC/FEC tables, scrambler seeds, resource mapping, and register
   programming. These are search targets, not claimed discoveries.
3. Track candidate constants to actual code paths. A matching polynomial or
   string alone is insufficient evidence of its role in the downlink.
4. Reimplement a small candidate encoder/decoder offline and test against held-out
   UT frames before interpreting DS7/DS8 signatures. Require consistent
   re-encoding and independently justified checks, not merely plausible values.

Disassembly can reveal machine instructions and approximate control flow, but
does not recover the original source perfectly. Some signal processing may be
implemented in hardware: firmware might reveal configuration without supplying
the decoder algorithm. Recovering a radio header format also does not imply
decrypting subscriber payloads.

## Other literature checked

[SDR-X's coding supplement](https://sdr-x.github.io/starlink-supplement7/)
summarizes patent US12003350, an uplink patent. Its short PDU header description
is a hypothesis source, not an independently decoded Ku-downlink test vector.
Do not equate that PDU header with all six observed leading OFDM symbols.

[Babusенко et al., July 2026](https://radiotec.ru/en/journal/Radioengineering/number/2026-7/article/26195)
describe a software waveform model in the public abstract. The accessible page
does not provide a measured header decoder or downloadable implementation;
the full paper was not inspected. Simulation alone cannot validate field meanings.

No verified air-interface header test vector was found in these reviewed sources.
That is a bounded search result, not evidence that none exists online.
