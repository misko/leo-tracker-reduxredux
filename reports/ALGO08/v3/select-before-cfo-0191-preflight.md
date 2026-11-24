# DS30-0191 prospective transfer preflight

DS30-0191 was the length-only selection from 455 signed original recordings. It issued 1,230 visits, the lowest count in the predeclared inclusive 1,000–2,000 range, and admitted 992. Its three segments contain 20 compressed members totaling 1,514,118,459 bytes. The recording covers scan channels 1–8 at the upper pilot edge on both radios at 10 MS/s. The original request supplies the 25 km operator offer and 51 signed causal TLE snapshots representing 37 distinct contents. [Machine receipt](measurements/select-before-cfo-0191-preflight.json)

The raw pair remained deferred at high host I/O pressure. Passive residency checks observed all 20 members and zero of 369,668 payload pages resident. The original compressed size fits the 1.65 GB ceiling, but no conditioning or waveform read occurred. Installed ALGO08v3 identity and the candidate's guarded anchored-CFO pack verified under the one-core, low-priority Gauss lock.

The only authorized cold input read was a 556,734-byte sealed packet. Its digest, 992 admitted visits, original session, and clock cutoff verified. The packet contains 1,984 per-radio clock and hardware-quality rows with zero detector candidates. Its provenance explicitly identifies a clock-only sidecar. A targeted search by exact workspace and inventory IDs found no authenticated named ALGO08v3 packet in tmpfs or the relevant publication roots. The original full-run tree contains legacy detector archives. Their bodies were left unread. Tmpfs filenames cover all 37 signed TLE content digests, and no original TLE body was read.

Neither solver was launched. The preflight supplies no fix, withholding, RF residual, geographic error, or detector-to-exit timing.
