# USB spare `.18`: released firmware and 2R2T restoration

2026-09-09. Explicit operator authorization: flash the latest released firmware
and restore 2R2T using PPU. This maintenance authorization supersedes the earlier
no-flash restriction **for this radio and operation only**.

## Result

**Successful flash, reboot return and final configuration verification.**
The physically USB-attached radio at `3-11`, serial
`1040007c4a94000211000b009186843ef2`, is now running
[`v0.49-plutoplus-spf-iq-direct-async-v4`](https://github.com/misko/plutosdr-fw/releases/tag/v0.49-plutoplus-spf-iq-direct-async-v4).
The GitHub release inventory and PPU's persistent promotion policy identify this
as the latest published full release; the previous v0.50 RX-only experimental
branch is not that released standard image.

All radio access used its physical Ethernet address `192.168.1.18`, with exact
USB/LAN serial matching and the shared PPU serial lock. `.14`, the original
excluded serial, and production radios were not contacted or changed.

| Final check | Observed result |
| --- | --- |
| Boot configuration | `mode=2r2t`, `compatible=ad9361`, `attr_name=compatible`, `attr_val=ad9361` |
| Live PHY compatibility | `ad9361`; this does not change the physical chip identity |
| Receive storage elements | `voltage0`..`voltage3`: two complex RX channels |
| TX safety | Both gains −80 dB; LO powered down; buffers, scan enables and DDS output disabled |
| Receiver range check | 5.8 GHz accepted/read back; original tuning restored |
| Stock persistent metadata endpoint | Exact serial and ABI 3 probe passed on port 30431 |
| Contiguous memory | 221,184 KiB = 216 MiB CMA |
| Flash integrity | Exact pinned image and QSPI FIT readback verified |
| Bootloader | `/dev/mtd0` SHA-256 unchanged from the pre-maintenance backup |
| Cleanup | Buffers idle; PPU-owned staged firmware removed |

Firmware, Linux and FPGA contents were replaced by the stock release image.
No custom firmware/FPGA development was performed. Reboot return was verified;
this is **not** a physical power-cycle qualification. No IQ capture or live
duty-cycle test was run, and no scanner service was deployed by this operation.

## Safe restoration sequence

PPU's existing supported path was used without relaxing its layout or identity
guards: experimental RX-only v7 → released v0.48 recovery → guarded 2R2T setup
→ released v0.49 promotion. The bootloader was not flashed. Private environment
backups were retained outside the repository.

The first supported setup profile cleared the compatibility attribute pair.
Although four RX elements appeared, the live PHY remained `ad9363a` and rejected
the 5.8 GHz check. PPU correctly refused to call this a canonical pass. Its second
supported profile set the AD9361-compatible attribute pair and passed the full
functional checks. Thus the final software profile is AD9361-compatible 2R2T,
not a claim that the physical transceiver became an AD9361.

Setup reboots rotated SSH keys. Original uncertain receipts were retained;
PPU explicitly re-attested the returned LAN serial/firmware/ABI and rotated the
task-local pin before read-only reconciliation. Strict SSH checking was not
disabled. A real reconciliation bug was exposed: the reader recognized only
`reboot_observed`, while the executor records target-qualified variants.
Local PPU commit `d7d529adaa8f7eb00b7147ee133c859cc42bb2ce` recognizes only the
selected target's approved profile tags, preserving the original receipts and
all safety checks. The regression first reproduced the bug, then **93 tests
passed**, including rejection of unrelated/malformed tags. One initial test
attempt used an environment without PPU's `pexpect` dependency; the final run
used the isolated PPU runtime with its declared dependencies. No test was
silently skipped or weakened.

The second setup was reconciled as verified in receipt
`fcc409ab599041ee87cd6b827b533141`; the final flash succeeded in receipt
`fa36f40a-8fc0-43a0-a77c-e07a31081673`.

## Evidence and remaining work

- [Final flash receipt](evidence/2026_09_09_radio18_v49_2r2t/v49-flash-receipt.json): staged/readback hashes, reboot phases and return/TX attestations.
- [Final verification](evidence/2026_09_09_radio18_v49_2r2t/final-verification.json): exact USB/LAN identity, setup checks, runtime hashes, memory and bootloader readback.
- [Stock metadata probe](evidence/2026_09_09_radio18_v49_2r2t/final-stock-probe.json).
- [93-test reconciliation regression receipt](evidence/2026_09_09_radio18_v49_2r2t/reconcile-passed.xml).

Full private recovery backups and intermediate receipts remain under
`/home/mouse9911/.local/state/pluto-plus-utils/r18-restore-2r2t.VHHdCU/`.
Do not publish those environment backups; they can contain credentials.

This removes the earlier incompatible-layout blocker. It does **not** qualify
the experimental GLRT provider, 300-second capture duty, adaptive scheduling
benefit, or deployed UI. Exact-package live canaries, release/remote merges and
production deployment remain separate gates. The PPU fix and this checkpoint
are local commits, not a claim of remote-main publication.
