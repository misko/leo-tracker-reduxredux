# Exact named solver on the original DS30-0016 20/8 ms factors

On the identical saved 20/8 ms detector packet, the exact named solver completed in **6.453 s elapsed / 6.434 CPU s**, compared with **6.918 / 6.916 s** for the original named solver. That is **1.072×** through verified publication. Both workers produced the same fix, all 115 ordered owners in each arm, the 179-location standard grid and recorded path, and all eight lossless figures. [Protocol](named-weak-all8-protocol.md) · [Sealed comparison](measurements/named-weak-all8.json.gz)

| DS30-0016 result | Fixed-zero horizontal error | Fitted-`c` horizontal error | Terminal RF RMS, fixed / fitted | Owner rows per arm |
|---|---:|---:|---:|---:|
| Deployed ALGO08v3 on its own archived full-aperture detector | 1,643.669 m | 1,661.443 m | 109.375 / 109.479 Hz | 109 |
| Original named solver on the complete saved 20/8 ms detector | 490.071 m | 980.010 m | 134.021 / 133.740 Hz | 115 |
| Exact named solver on the same 20/8 ms detector | 490.071 m | 980.010 m | 134.021 / 133.740 Hz | 115 |

Both saved workers used the original deployed v3 fingerprint and accepted both arms. The 115 ordered rows include 92 conditional and 23 predictive owners per arm. The shared terminal digest also matches the earlier cumulative/named-survivor research terminal on this very packet. Since the original named solver reproduces it, the accuracy improvement over deployed v3 on its own detector holds under original named inference on this recording. The held 20/8 ms fitted arm reduces RF RMS by 0.282 Hz while increasing horizontal error by 489.939 m relative to fixed zero. [Archived own-detector baseline](raw-0016-best.md) · [Earlier 20/8 ms research publication](weak-all8-adaptive.md)

## Input and exactness

One metadata-only inventory lookup and one saved handoff per worker used `sha256:aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac` exactly. This is the complete signed 20/8 ms receiver output after the original held gate. It covers 808 issued, 713 admitted and 95 excluded visits, 1,426 native radio lanes and 506 signed factors. The held gains were −25.287 and −11.749 nats and kept the unfiltered chronology with zero additional CFO tails. The historical own-detector comparator used the same original authority, offer, archive and observation opportunities and produced 440 factors. The measured saved workers used no original waveform or backing archive content. [Held input and causal receipts](weak-all8-combined.md)

The installed launcher checks the genuine named detector asset before the saved boundary runs. That asset's pin differs from the genuine held recipe. The scoped handoff revalidates the saved packet and recipe and supplies that pin for the scanner's independent check, without altering a receiver byte or replacing the pinned named numerical configuration. Each full 179-point grid is exact after excluding its elapsed-time field. The path and all eight encoded and decoded PNG comparisons are exact. Both position documents bind the published PNG, native packet, terminal and owners. The original named renderer and figure layout run in both workers. [Saved handoff and pair driver](named_weak_all8.py)

The exact port activated for all 48 catalogue calls, retaining 1,945 of 69,552 rows for the exact rank operations. It used an earlier verified index for 19 of 20 causal bodies and paid the one cold body's preparation. All 356 non-endpoint grid evaluations used prepared phase states. Publication verification reused all eight verified PNG reads. There was no original history retry and no constrained gate invocation on this recording. These exact ports are the same independently frozen source previously validated against the original named solver on DS30-0160 and DS30-0316. [Exact named route](exact-named-route.md)

## Saved and historical timing boundaries

| Boundary on the same saved packet | Original named wall / CPU | Exact named wall / CPU |
|---|---:|---:|
| Numerical solve | 3.630 / 3.630 s | 3.127 / 3.119 s |
| Renderer | 1.759 / 1.759 s | 1.701 / 1.692 s |
| Fresh process through verification and exit | 6.918 / 6.916 s | 6.453 / 6.434 s |

The two workers ran once in named then exact order on the same low-priority Gauss core. Neither recorded a major fault. Process-wide input blocks were zero on named and 48 on exact. The candidate's causal preparation scope took 1.473 s and includes verification and artifact loading. Its older portable index producer took 4.320 s in a separate measured process. Charging that earlier producer serially gives **10.774 s** for the candidate saved boundary including the producer. The original named worker uses the stock catalogue preparation.

The earlier authenticated 20/8 ms acquisition component took **3.141 s** on this recording. Adding it to the fresh **6.453 s** exact named saved clock gives **9.594 s** in a separate-clock estimate. Against the archived resident v3 original waveform-to-exit clock of **10.824 s**, that is **1.128×**, or **2.829 s** above the 1.6× time allowance. The earlier, different cumulative research publisher reached **4.166 s** with the full grid and a Cairo renderer. Those are distinct saved publication configurations. This test measured the exact named route with the original renderer and standard layout.

Run `named_weak_all8.py launch FRESH_TMPFS_ROOT f4370e44346c8c83935dc28b8d8a379551f19a95`, then `verify FRESH_TMPFS_ROOT`, with the released Python and the shared Gauss CPU 2 lock at nice 15, I/O priority 7 and one numerical thread. The protocol binds the signed weak packet, original raw comparison, all exact-source hashes and earlier producer. Four focused tests passed. The comparison required two fresh saved workers and no acquisitions.
