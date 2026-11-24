# Held physical DS30-0160 saved solver transfer

The current combination completed both calibration arms and published all eight images, but missed the 1.6× target and increased horizontal error in both arms. This is one independent physical recording and one fresh candidate process. Both timed solvers consumed the same signed full-recording native detector packet from the deployed 20 ms receiver. The clock begins at that saved packet and includes validated products and process exit. [Frozen enrollment](held-adaptive-0160-protocol.md) · [Machine receipt](measurements/held-adaptive-0160.json.gz)

| Saved-input clock | Installed named v3 | Combined adaptive | Speedup |
|---|---:|---:|---:|
| Through exit, wall | 15.9986 s | 14.3529 s | 1.115× |
| Through exit, CPU | 15.9938 s | 14.3185 s | 1.117× |
| Timed solver work, CPU | 12.5651 s | 11.8602 s | 1.059× |

| Calibration arm | Named horizontal error | Candidate horizontal error | Change | Named RF RMS | Candidate RF RMS |
|---|---:|---:|---:|---:|---:|
| `c = 0` | 798.498 m | 822.287 m | +23.789 m | 126.335 Hz | 127.816 Hz |
| Fitted `c` | 1,089.003 m | 1,324.718 m | +235.715 m | 126.093 Hz | 127.550 Hz |

Each solver delivered one fix and zero withholds. With fitted `c`, RF RMS decreased by 0.243 Hz on named and 0.266 Hz on candidate. Horizontal error increased by 290.505 m and 502.431 m, respectively. Both arms retain 988 of 1,037 named owners and drop the same 49. Every shared row preserves its NORAD and role, and the candidate gains zero owners. The candidate's `history_support` route requests the named survivor fit but pays no named survivor refit. The regional guard stops after 24 probes at `eligible_exterior_separation` and returns `would_withhold=false`. The pair does not isolate the cause of changed owners or the position error.

The two runs share the session, original offer, cutoff, and all 3,691 issued visits, of which 2,354 were admitted and 1,337 had invalid captures. The earlier DS30-0008 portable artifact serves four of 36 distinct bodies on each of two preparations. The remaining 32 use cold parsing each time. All 262 catalogue reads were verified by the installed reader against the signed, fully resident tmpfs snapshot set. Those reads consumed 468,212,834 logical bytes from 92,933,882 bytes already staged. The experiment copied zero bytes and performed no reads from original waveform or backing catalogue paths. Child block counters include runtime assets and are retained in the machine receipt. Grouped rank compacted 832 calls across two admitted ranks, and the exact proposal check dropped two duplicates from 24 Graph finalization calls.

The installed comparator used its standard renderer and complete 179-location grid. Independent verification matched its previously audited terminal and science. Both sides passed decode and digest checks for eight images and verified path and position-product bindings. The candidate directly rendered four orbit and two residual figures, reused all eight verified PNG reads, and evaluated 124 exact locations per arm in the research map. The prior standard-layout research run has a different fitted state. Map verification covers the exact measured locations, fitted endpoints, published path and figures. It cannot establish the omitted locations' score coverage on DS30-0160.

Enrollment screened five known complete native bindings and found one eligible independent medium session. DS30-0160 had prior owner and endpoint research. Its layout and 20/8 receiver were not tuned on this packet. The comparison reuses the existing same-packet v3 process on the same low-priority CPU 2 configuration. It therefore carries historical process variance. The candidate was run once, with no adjustments or accuracy-based selection. The candidate clock SHA-256 is `2afa1675000a0d12fa58b69911554e79b161a1fa789f7e27dedfa4eaaa61f8b6`, and the uncompressed result SHA-256 is `e11890735ec2e67e24c334580dc475a8f592c723a84049f78c1ce1950fc3bff4`.
