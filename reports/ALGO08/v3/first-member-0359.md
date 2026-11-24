# DS30-0359 passive original-input admission

DS30-0359 is deferred for original-file replay. At 14:10:43 UTC on
2026-11-24, the original file owner observed **0 of 19,305 resident
pages** in the first signed member. Five explicitly named tmpfs
locations had no original copy. The nominal NVMe spool link points to
the same RAID recording. [Saved-solver comparison](ds30-0359-combined.md)

| Frozen first member | Observed value |
| --- | ---: |
| Acquisition order | First of 14 signed segments, sequence zero |
| Issued visits in member | 64 |
| Encoded bytes | 79,072,939 |
| Decoded bytes | 102,400,000 |
| Signed manifest and index bytes read | 6,812 + 173,445 |
| Backing device | XFS `252:5`, device ID 64517 |
| Payload bytes read / copied | 0 / 0 |
| Detector or solver children launched | 0 |

The existing saved request and inventory bound acquisition order and
original recording authority. The original manifest and index were
authenticated, including exact signed row sequence and byte coverage.
The descriptor-only residency query succeeded as `leo`, the original
owner, UID 994. The exact path checks covered the named recording
directly under `/tmp` and `/dev/shm`, the two known combined-solver
directories for this case, the original saved baseline directory, and
the existing NVMe spool name. The check did not traverse other cases
or payloads. The result is a point-in-time admission for this first
member and gives no residency estimate for the rest of the recording.
[Earlier first-member rule](ds30-combined-first-member-admission.md)

Five component and adjacent tests passed.
[Admission source](first_member_0359.py) ·
[Machine receipt](measurements/first-member-0359.json), SHA-256
`f2e56e293b1cf6f293a5b013c38d984c72e1eb747ec6f48d17648af6cccc6c10`.
