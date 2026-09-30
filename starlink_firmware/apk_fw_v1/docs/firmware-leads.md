# Public firmware leads for waveform decoding

Reviewed 2026-09-28. Scope: public online artifacts only. No private researcher
access, hardware extraction, or new RF collection is assumed. This is a source
review plus inspection of public firmware binaries. The APK acquisition below
has now succeeded and modem executables have been recovered. Header decoding
remains unverified.

## Follow-up: encoder and mapping sources

A targeted public-web review on 2026-09-28 searched for Starlink firmware,
convolutional generator polynomials, header interleaving, and PHY PDU decoding.
No verified generator set or carrier/interleaver implementation was obtained
from the sources checked. This is a bounded search result, not a claim that
none exists anywhere online.

* [Andrea Angelo Raineri, *Reverse Engineering of the Starlink User Terminal*](https://webthesis.biblio.polito.it/38704/)
  is a 58-page Politecnico di Torino thesis catalogued for 2025/26. The official
  record explicitly marks it confidential and says no full text is present.
  Only its abstract/metadata were available; it supplies no inspectable encoder
  evidence. Under our public-online-only scope, this is not an actionable source
  for implementation details. No author contact or private access was requested.
* [Quarkslab's original firmware analysis](https://blog.quarkslab.com/starlink.html)
  identifies `phyfw`, `rx_lmac`, and `tx_lmac` as low-level modem-related processes
  and states that these processes do not work in its hardware-incomplete runtime
  emulator. Its published emulation work therefore cannot be treated as a
  software RF decoder. Our isolated instruction checks verify selected memory
  behavior, not those missing hardware operations.
* An [original July 2026 public research question](https://www.reddit.com/r/StarlinkEngineering/comments/1v9rfdl/starlink_ku_ofdm_phy_pdu_header_which_res_to_take/)
  reports BPSK-like early symbols after rotational descrambling and asks for
  generator, termination, CRC, and mapping details. This is an unverified
  first-person report, not a specification or validated decoder. Suggestions
  there about whether short headers need interleaving were not adopted as facts.

The operational gap remains the connection between the verified in-memory MAC
format and the observed RF sequence: encoder definition, scrambling, and carrier
placement. The source review adds no new decoded field and does not justify
treating guessed LTE-like generators as established Starlink parameters.

## Successful APK acquisition and modem runtime recovery

Later on 2026-09-28, [APKCombo's public download page](https://apkcombo.com/starlink/com.starlink.mobile/download/apk)
provided a working download for app version 2026.24.0. The XAPK is 404,609,952
bytes, SHA-256 `21bb48af60c47b0df9fc786c78d03c1d8927f0bf5ea4175e4b9ef5eb141ec862`.
The 176,978,724-byte base APK contains both dish update bundles. This independently
confirms the embedded-firmware route, using a newer app than the cited teardown.
APK signing and sxverity authentication have not yet been independently verified;
these are third-party-hosted research artifacts, not trusted deployment images.

| Extracted asset | Bytes | SHA-256 |
| --- | ---: | --- |
| sw_update_catson.sxv | 47,355,904 | 2213b5cd9edf5e01be813f97724f0c4b21aed25138a220791fbce46c92d4ba1f |
| sw_update_catapult.sxv | 43,866,112 | e5ceea7e46a7b5321d61bd68d2ccfb88c04fe1f4ea2f6ac4d557531b30765222 |

Static extraction chain: base APK ZIP member → sxverity bundle → ROMFS at
offset 4096 → runtime.sxv → nested ROMFS → runtime.tar.zst → Zstandard
decompression → tar member reads. No mount, terminal modification, or firmware
execution was used. Both tar inventories contain 8,298 entries.

The runtime contains AArch64 ELF executables, including:

| Catson runtime file | Bytes | SHA-256 |
| --- | ---: | --- |
| bin/phyfw | 1,056,208 | 52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326 |
| bin/rx_lmac | 1,577,336 | 9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe |
| bin/tx_lmac | 1,577,336 | a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6 |

Catapult and v4 variants are also present. The runtime version file identifies
March 27, 2026 build `mr76839`, constellation commit
`d2db9be25af5f37f9b642e7ac7ad1b2833efac3a`, matching the published teardown's
metadata despite the newer app container.

Initial string inspection finds header-decoder error counters, PDU/GMH parsing
diagnostics, and PHY/LDPC references. These identify analysis targets only;
strings and internal metadata are not proof of on-air field layouts. Next work
is tracing these references through the executable code and hardware interface.

All packages, inventories and extracted bytes remain under ignored
`local/firmware/`. Canonical extracted executable names preserve their original
directory: `catson-bin--phyfw`, `catson-bin--rx_lmac`, and
`catson-bin--tx_lmac`. Earlier basename-only scratch exports collided with
AppArmor profile names and must not be used as executable inputs. ZIP integrity
was checked while reading members; cryptographic provenance is still open.

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
