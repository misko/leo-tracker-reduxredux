# Extracted firmware images and files

The existing Catson and Catapult packages have been recursively unpacked into
[`../../local/unpacked_images`](../../local/unpacked_images). Acquired firmware
and extracted data remain ignored by Git. No firmware, startup script or device
operation was executed. The original source files remain unchanged.

## Do the XP70 images contain files?

**They contain address-labelled memory contents, not an identified filesystem.**
The S-record containers supply data records and an entry address. We can recover
those bytes exactly, retain their memory addresses, and extract readable text.
We have not recovered a directory tree or named internal files from any XP70
image. Diagnostic source filenames are strings compiled into the firmware;
they are not embedded source files.

Every data-record length and checksum passed verification. Adjacent records
were combined; gaps remain gaps, with no invented zero padding. The existing
host-loader evidence classifies low addresses as data, addresses around
`0x200000` as strings, and addresses around `0x400000` as text/code. It does
not establish an instruction set or a complete executable format.

| XP70 image | Recovered bytes | Contiguous regions | Entry address | Printable strings, minimum 6 characters |
|---|---:|---:|---|---:|
| bamboo | 69,340 | 13 | `0x4000e0` | 194 |
| gopher | 79,941 | 14 | `0x4004b2` | 251 |
| panda | 66,315 | 14 | `0x4000ea` | 194 |
| peanut | 37,068 | 10 | `0x4000d8` | 69 |
| pez | 86,516 | 15 | `0x4004b2` | 289 |
| pulsar | 41,614 | 12 | `0x4000d8` | 84 |

Each region was checked for ELF, ROMFS, SquashFS, ZIP, newc CPIO, gzip and
Zstandard signatures. **No candidates were found in any XP70 region.** This
bounded signature check cannot exclude an undocumented container or compression
scheme. Printable strings may include accidental instruction-byte matches.
Known meaningful diagnostics concern phased arrays, Shiraz, beamforming and
front-end control; see [the code-linked evidence](EMBEDDED_IMAGES.md).

## Directory structure

```text
starlink_firmware/apk_fw_v1/local/unpacked_images/
├── manifest.json
├── xp70/
│   ├── xp70_bamboo/
│   ├── xp70_gopher/
│   ├── xp70_panda/
│   ├── xp70_peanut/
│   ├── xp70_pez/
│   └── xp70_pulsar/
│       ├── xp70_pulsar.srec
│       ├── memory_map.json
│       ├── strings.tsv
│       └── region_<start>_<exclusive-end>.bin  [one per populated region]
├── sw_update_catson*.sxv                    [copies of existing sources]
├── sw_update_catapult*.sxv
├── <package>.sxv.unpacked/
│   └── <member>                            [original member bytes]
│       <member>.unpacked/                  [recognized nested content]
└── existing_linux.fit[.unpacked/]
```

All six XP70 subdirectories have the same structure. Their memory maps include
source hashes, entry addresses, per-region hashes, addresses, signature results
and complete extracted strings. Region filenames use hexadecimal addresses.

The runtime trees are at:

```text
sw_update_catson-runtime.sxv.unpacked/runtime.tar.zst.unpacked/runtime.tar.unpacked/
sw_update_catapult-runtime.sxv.unpacked/runtime.tar.zst.unpacked/runtime.tar.unpacked/
```

These preserve regular runtime member paths, including executables, scripts,
configuration, data and firmware images. Other extracted content includes ROMFS
members of update/version/TFTP packages, FIP boot components identified by UUID,
FIT inline data properties (including kernel, device trees and ramdisk), and
regular files in the decompressed initramfs CPIO archive. Unknown binary leaves
are retained unchanged rather than assigned speculative filenames or types.

The manifest records **17,529 regular-file occurrences** and **701 other member
records**, totaling 18,230 entries. Regular-file bytes total 1,305,113,753 before
the separate XP70 analysis products. There are 15,331 repeated-content
references: identical content is saved at its member paths but expanded only
once, with `same_content_as` pointing to the first occurrence. Thus an identical
nested container may have its extracted children under another package's path.
The six XP70 payloads are the six unique S-record contents found across these
packages; the manifest preserves their occurrences.

Symlinks, hardlinks and special nodes are recorded as metadata rather than
created. This is a research extraction, not a bootable reconstructed rootfs.
Original TAR/CPIO containers are preserved for metadata-sensitive reconstruction.
No executable permissions or archive ownership were applied to output files.

## One decompression exception

The Catapult FIP component
`sw_update_catapult.sxv.unpacked/linux.ab.fip.unpacked/d6d0eea7fcead54b97829934f234b6e4.bin`
begins with Zstandard magic. The decompressor produced output but exited with
`unknown header`. The output is retained under
`<component>.unpacked/unverified_prefix_decompressed.bin`; it is **not certified
as a complete decompression**. The original is intact, and the manifest records
the error. Trailing packaging bytes are a possibility, not an established cause.

## Reproduction and checks

Run `python3 unpack_images.py` from this report directory; system `zstd` is
required. The extractor handles recognized SXV/ROMFS, Zstandard, gzip, TAR,
newc CPIO, FDT/FIT inline data, FIP and S-record layers. It rejects path traversal
and refuses to replace existing output with different bytes. Unknown leaves,
external FIT data and unidentified embedded formats are not claimed decoded.

Component tests cover path-escape rejection and S-record address/byte recovery;
the S-record validator also has its existing checksum tests. The extraction ran
successfully over the real corpus, all 78 XP70 output-region hashes were
rechecked against their memory maps, and Git ignore coverage was verified.
Re-running reproduced the same output without modifying existing bytes.
