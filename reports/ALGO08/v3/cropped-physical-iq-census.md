# Existing physical I/Q across separated capture times

No receipt-named tmpfs or independent NVMe fixture supplied physical DS30 waveform bytes across more than 20 seconds within one session. No receiver or position process launched. The widest complete original sample found on an eligible device was 64 stereo visits from DS30-0008 over **2.8123266 s**, measured from the first to the last hardware sample start. The historical noncontiguous occupancy trial covered **144 stereo visits over 25.3710124 s** on the same recording. Its later 16 visits came directly from the original recording, and the saved evidence contains their I/Q hashes, features and detector rows. The code kept the samples in memory during that trial. [Occupancy protocol and receipt](occupancy.md) · [Scope and retained outputs](occupancy_trial.py)

| Receipt-named physical fixture | Original stereo visits | Start-to-start hardware span | Payload custody |
|---|---:|---:|---|
| DS30-0008 first signed member | 64 | 2.8123266 s | Complete tmpfs member and index, prior verified I/Q |
| DS30-0016 first signed member | 64 | 2.7910898 s | Complete tmpfs member and index. The next member is partial |
| DS30-0169 first signed member | 64 | 2.7918656 s | Complete tmpfs member and index, prior verified I/Q |
| DS30-0107 complete | 29 | 1.2549139 s | Complete tmpfs recording |
| DS30-0008 first three original members | 192 | 8.4826626 s | Prior private XFS backing scope, receipt still present |
| DS30-0008 occupancy slice | 144 | 25.3710124 s | Visits 0–127 plus every fourth visit in 512–575. Retained non-waveform evidence |

The original DS30-0008 later occupancy segment and the exact private path cited by the first-member transfer both resolve through `findmnt` to `/srv/bulk`, XFS device `252:5`. `lsblk` shows its data LV on `md127` RAID6, with a cache on `nvme2n1`. The first-three private staging runner restricts its XFS copy to this same mount. `/var/tmp` is a physically separate ext4 LV at `252:0` on `nvme0n1p3`. The checked receipt-named roots there retained numerical and publication outputs. The long public North/South I/Q fixtures are simulations, and the archived 18 stereo DS26 clips come from five other recordings. The census opened signed archived metadata and local indexes only. It did not read waveform or catalogue contents from any device. [Prior XFS scope](full-short-cold.md) · [Existing local receipt census](alternate-physical-source.md)

## Minimum bytes for a two- or three-member diagnostic

The prospective rule keeps the already verified initial full member, then the earliest complete, nonadjacent 64-visit member whose final hardware start makes the total span exceed the specified threshold. For three members, also include the intervening full member nearest the elapsed midpoint, measured by the nearest included hardware start within that member. Numeric segment and member indices break ties. This rule uses original chronology and complete stereo membership. Applying it at **20 s** requires the following signed files. Each pair arm would decode and verify both radios throughout each included member, restart history at the original boundaries as required by the receiver, and use the original unmodified operator offer and causal archive. This would be a selected-arc diagnostic with temporal and RF sampling bias from the omitted visits. It supplies no complete-recording qualification.

| Segment and member | Original visits | Hardware start range from recording origin | Compressed bytes | Index bytes | Availability |
|---|---|---:|---:|---:|---|
| 0 / 0, first | 0–63 | 0.0000000–2.8123266 s | 77,442,779 | 172,750 | Existing signed tmpfs |
| 0 / 3, optional middle | 192–255 | 8.5270918–11.3197026 s | 77,371,804 | 172,798 | Signed metadata only |
| 0 / 7, later | 448–511 | 19.8770877–22.6696093 s | 77,510,209 | 172,810 | Signed metadata only |

The two-member design requires **77,683,019 additional original bytes** and pays for 128 stereo visits. The three-member design requires **155,227,621 additional original bytes** and pays for 192 stereo visits. Both cover **22.6696093 s**. No additional segment manifest is needed. It is already staged and matches archived inventory SHA-256 `3f08c51c74fa878e0b5993311a840172c2b06d2d0be02988d13f0c29f502034b` at segment 0 manifest SHA-256 `5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759`. The late payload and index digests are `77792341953e9c44308bcde14ce0a4b324a9f9a1a2013d177e4577fa991a1468` and `455e5d8a4ee0547444498e1886f84f530eb93e99688f921879a5a50eb410c08c`. The middle payload and index digests are `5ca15e039a62bdbad06bcf3afd20520f41ff588e13ecc0831cbb097a06e3978d` and `fb32c40061f37d5e6d277f7258b81e11872d88f3931f76c2db9c45d891aacee9`.

For **60 s**, the same rule elects segment 2 member 5, visits 1,344–1,407 at 59.5785691–62.3678287 s. The optional midpoint is segment 1 member 2, visits 640–703 at 28.3836018–31.1744841 s. The signed inventory pins segment manifest SHA-256 `72f1b2a898c64c579145e98aa3a1f8884678f662f735f5a4af55d4999da381a1` and `54a2bfdef9f5b978a8cee36e204faa56d3a55ef28b096edb38345af305d9efef` respectively. The available receipts lack their exact per-member compressed and index lengths. All proposed blocks have both radios in the recorded visit metadata. The recorded times come from the saved same-session native packet with SHA-256 `ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85`. No staging or detector replay was performed.
