# DS30-0003 retained detector agreement

The mixed receiver's **387 additional retained peaks** coexist with substantial turnover. It adds occupied lanes at **1,074** original opportunities, leaves **687** previously occupied opportunities empty, and returns a peak outside the signed match window at **725** opportunities where both receivers returned a factor. The last group does not change net occupancy. The signed capture identities, RF, original opportunities and window clocks matched. [Frozen protocol](ds30-0003-native-agreement-protocol.md) · [Exact counts and I/O](measurements/ds30-0003-native-agreement.json)

| Candidate aperture | Shared radio opportunities | Installed / mixed positives | Unique matched | Installed-only lanes | Mixed-only lanes | Both positive, outside match | Ambiguous peaks, both sides |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 ms short | 11,744 | 4,651 / 4,957 | 3,270 | 687 | 993 | 694 | 0 / 0 |
| 20 ms anchor | 1,684 | 667 / 748 | 636 | 0 | 81 | 31 | 0 / 0 |

The signed unique-on-both-sides gate is ≤250 Hz and ≤2 absolute fractional samples, without alias or epoch wrapping. On the short lanes, 1,381 installed peaks and 1,687 mixed peaks lack a unique counterpart. That includes the 694 dual-positive lanes outside the gate on both sides. Only 70.3% of the installed short positives have a counterpart. The matched short differences have 96.66 Hz CFO RMS and 0.499 sample epoch RMS on their selected support. All 636 matched full/full anchor factors are byte-identical under the canonical factor encoding. The unmatched anchor factors occur on the same full aperture, where the different selected peak rules can change retained evidence. The mixed EOF route was unfiltered and paid zero 20 ms refinements on short lanes. [Established native comparison](first30-native-agreement.md)

The saved packets contain detector candidates, provenance and hardware opportunity metadata. They carry no final owner rows. The comparison identifies missing published long-aperture counterparts and added detections. A missed signed match can reflect a different selected peak or a measurement outside either tolerance. The receipts leave its satellite assignment and effect on the final fit unresolved.

| Saved NVMe packet | Logical bytes read once | Process storage bytes | Process input blocks | Read wall |
| --- | ---: | ---: | ---: | ---: |
| Installed | 5,038,333 | 5,042,176 | 9,848 | 3.82 ms |
| Mixed | 5,162,022 | 5,165,056 | 10,088 | 6.73 ms |
| Total | 10,200,355 | 10,207,232 | 19,936 | 10.55 ms |

One idle exclusive lease used CPU3 at nice 15 and idle I/O. Both complete byte digests verified from the single read of each file. The lease covered 244.61 ms wall and 238.86 ms CPU, with 133.10 ms in the in-memory join. These are measured read and comparison clocks for saved outputs on the local NVMe device. An earlier lock attempt yielded before either read. No recording, bulk archive, other case results, survey, waveform or ownership body was opened. Five focused and adjacent tests passed. [Meter and comparator](ds30_0003_native_agreement.py)
