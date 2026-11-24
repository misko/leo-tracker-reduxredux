# Frozen routed solver on the simulated South near omission

The routed solver and installed ALGO08v3 both published a false fix when the supplied 25 km square excluded the simulated receiver by 100 m. The two calibration endpoints, RF residuals, ordered satellite owners and science in the standard grid and path matched exactly. The routed worker took 5.717 s from saved-packet launch through exit versus 7.891 s for installed v3, a 1.380× speedup in this scope. [Frozen protocol](nomination-handoff-south-protocol.md) · [Scored receipt](measurements/nomination-handoff-south.json.gz)

## Offsite comparison

The earlier South studies used either a different receiver packet or a solver predating the nomination handoff. Their archived containing baseline used the original 20 ms acquisition but included raw reads in its clock. The archived omission timer covered the solve without a verified full publication. The protocol therefore enrolled one new matched saved pair on the prior difficult omission, with the old containing result for context. Both workers consumed the exact same original signed 20 ms packet with all 1,200 visits, the original offer and the 35-body causal archive at cutoff `1794638719996253000`. The routed worker matched the 37 scientific sources in the sealed DS30-0419 run. The new adapter only admits the existing direct RAM paths and recognizes a canonical single-segment manifest path already ending in `manifest.json`. The workers never opened the original recording. [Earlier South study](named-south-transfer.md) · [Earlier 20/8 South test](exact-named-south-omitted.md) · [Frozen DS30-0419 runtime](nomination-handoff-0419-local.md)

| Offer and worker | Geographic decision | Horizontal error, fixed / fitted `c` | RF RMS, fixed / fitted `c` | Ordered owners, fixed / fitted `c` |
|---|---|---:|---:|---:|
| 100 m omitted, installed v3 | False fix | 817.172 / 1,102.143 m | 6.502345 / 6.392003 Hz | 266 / 266 |
| 100 m omitted, frozen routed | False fix | 817.172 / 1,102.143 m | 6.502345 / 6.392003 Hz | 266 / 266 |
| 100 m inside, archived installed v3 | Fix | 816.789 / 1,101.409 m | 6.502299 / 6.391940 Hz | 266 / 266 |

On the omission, the common fixed-`c` position was `(-32.95778733127612, 21.464979730800728)` and the common fitted-`c` position was `(-32.960694013542536, 21.465618729506673)`. Fitting `c` lowered RF RMS by 0.110342 Hz and increased horizontal error by 284.972 m. The fresh installed result also matched the archived omission's arms, owner digests and orbit policy. The archived installed result supplies the only containing result for this test.

## Guard and publication

The orbit-health check found 1,618 earlier rows in each of the two original history banks and chose `lean` with `healthy_samples`. The cold nomination guard captured two prefixes at a cost of 9.690 ms CPU for the geometry identity and 0.588 ms for the checkpoints. No named fallback consumed a checkpoint. The original named survivor fit passed for both arms. No live orbit extension or original restart ran.

The routed handoff captured one prepared catalogue for the exterior guard. Its terminal check reported `bound_arms=[]` and `evaluated=false`. The fixed and fitted endpoints were 242.474 m and 182.783 m inside the east face, respectively. The current guard triggers when an endpoint lands at the optimizer bound. These interior estimates show the false-fix mode the trigger misses. The evidence covers one simulated omission and leaves the regional false-fix rate and enclosing-offer transfer undetermined.

Both workers' original publication reached a complete 137-point grid with zero endpoint objective-replay deltas. The scientific grid and path digests matched. Persisted sidecar document digests differ with their own run bindings. All eight published images were bound and fully decoded at matching native dimensions. The four ordinary orbit sheets were byte and RGBA identical. The Cairo residual sheets and explicit-layout position and track sheets differed in bytes and pixels. Both workers retained all 266 ordered owner and role rows in each arm.

## Timing scope

| Mode | Numerical wall / CPU | In-worker publication wall / CPU | Child launch to exit wall / CPU |
|---|---:|---:|---:|
| Installed v3 | 4.473 / 4.468 s | 6.235 / 6.206 s | 7.891 / 7.853 s |
| Frozen routed | 2.935 / 2.935 s | 4.319 / 4.319 s | 5.717 / 5.715 s |

Each child ran on CPU 2 with one numerical thread, nice 15 and I/O priority 7 under the shared Gauss flock. Both successful children exited zero and reported zero input blocks and major faults. External admission cost 0.576 s for the first lease and 0.559 s for the corrected lease. The routed worker initially stopped before inference and publication after 1.369 wall / 1.367 CPU s because the legacy manifest adapter appended a second `manifest.json`. The corrected lease reran only the routed worker and used the sealed original installed result. The comparison uses the two successful child clocks. The attempted routed work totals 7.086 wall s before external admission. No portable index was loaded or built.

The initial installed child's cache check lacked owner privileges for authoritative `cachestat`. The corrected routed admission used the archive owner and verified all 35 staged files and 15,295 pages after rechecking 1,788,089 bytes in 0.0043 wall s. An earlier owner-side setup stopped before launching any child while rechecking another staged body because it handled a bare snapshot digest as prefixed. These are sequential saved worker clocks across two leases with a verified local catalogue for the routed run. The archived installed containing clock of 14.370 s includes waveform acquisition and serves only as context. There were no waveform or backing reads, new RF, physical-site observations, or new recording captures in this experiment.

The original acquisition input SHA-256 is `26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3`. The complete first-control seal is `61a680e4f098c9d3aa3c25b44df87c29063f9d68d1456c4c9b4c7528fb752312` and the corrected seal issued before joining the simulated position is `44d497a4aa2ec007ba3b6524f83303a9cf1f55ae308bd67a23cacf5b81a00d18`. The uncompressed scored receipt SHA-256 is `15d177207c63e9d0669dbb3ed222393767eb59feca632037fb5aaaa77fbd1590`. The 16 focused tests passed. [Saved worker](nomination_handoff_south.py) · [Scorer](nomination_handoff_south_score.py)
