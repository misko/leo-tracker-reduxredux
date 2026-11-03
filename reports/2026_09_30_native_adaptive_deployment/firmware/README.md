# PPU v0.59 deployment to 192.168.1.15

Outcome: **PASS** on 2026-09-30 UTC.

PPU persistently installed the reviewed v0.59 image on the exact LAN target and
completed its physical-flash, protected-region, return-identity, and TX-safety
gates. The operation used `firmware flash-lan` internals through the retained
v0.59 exact-image adapter. PPU `force-flash` was not used because that command is
restricted to a directly attached USB device whose USB and IIOD serials are both
blank; this radio has a stable serial and is reachable over LAN.

## Target

- Host: `192.168.1.15`
- Serial: `104000b29905000e17000800065934759d`
- Before: `v0.54-plutoplus-spf-counter-utc-v1-rc1`
- After: `v0.59-plutoplus-spf-dual-rx-counter-fix`
- PHY: `ad9361`
- Boot ID before: `7257464f-8265-4b34-ae9d-1ea85fab082c`
- Boot ID after: `16bef527-baec-4d26-8d5d-43356c53515d`

## Exact image and profile

- Firmware source: `ca7f38f9f3a1ee059249b438af715855121ccfb2`
- Source tag: `dual-rx-counter-fix-v059-source/firmware-v1`
- Build: `36215189374`
- DFU: `plutoplus-spf-dual-rx-counter-fix-ca7f38f9f3a1-pluto.dfu`
- DFU bytes: `12785935`
- DFU SHA-256: `1fa69d2784efbcabaaaed5bc5f5d625deabfd7da725627c9634a694db5bd9df0`
- Generated FRM SHA-256: `7d4ba5585f2c8fd23b28025d46954e408ecf9b14d8fa6ddadfbb4c1de3b7f065`
- FIT bytes: `12785919`
- FIT SHA-256: `010cf3d09ed3cbcb7c640514066cccf6409cd0b5168404d0279924507c7f99c5`
- PPU profile: `dual-rx-counter-fix-v059-1fa69d2784ef-lan`
- IIO layout: `tx-capable-2r2t-profile-tandem-v1`

## Physical flash decision

PPU observed a 32 MiB `st:n25q256a:20ba19` flash with the expected four MTD
partitions and reviewed updater SHA-256
`d8a3693f88ca9f3f7e4f9e7b4ac4a62abb8976d610df058fc74bbd6a6ee915f0`.
The payload occupied `[0x200000, 0xE31EFF)`, with rounded erase end `0xE40000`,
inside the `0x1000000` safety limit. The environment occupied
`[0x100000, 0x120000)` and was outside the planned payload and erase ranges.

## Receipt and postboot verification

- Receipt ID: `b94ac3ab-cbab-4f6b-90ad-cb4cd0091392`
- Outcome: `success`
- All 18 receipt phases passed, including physical flash guard, protected-region
  verification, exact `mtd3` FIT verification, reboot, return identity, TX-safe
  state, host-key rotation, and final read-only remote attestation.
- Independent pinned-SSH readback produced the exact FIT SHA-256 above.
- Both IIO buffers were disabled and the temporary staged FRM was absent.
- PPU recorded TX LO powered down, both TX gains at `-80 dB`, all DDS raw/scale
  values zero, TX scan disabled, and tandem/RX/TX device-tree nodes enabled.
- Independent IIO discovery returned the exact serial and v0.59 identity.
- Adaptive capabilities: protocol `3`, rate mask `0x71`, rate mode `2`, RX mask
  `3`, dwell range `120..360 ms`, queue capacity `200000000` bytes, and source
  counter width `64` bits.

Reviewable artifacts:

- `authenticated-lan-plan.json`
- `flash-receipt.json`
- `postboot-attestation.json`
- `artifact-binding.json`
- `integrated-release-verdict.json`
- `SHA256SUMS`
- `hardware-evidence.tar.gz`

Private rotated SSH enrollment and the recovery bundle are retained under
`private/`. No credential contents are stored in this report.
