# Build status

| Budget | Build path | Receipt SHA-256 | Status |
| --- | --- | --- | --- |
| 1 frame / 3 symbols | `/var/tmp/leo-host-sparse-proposal-13-v2` | `fb0678ddbc8c21d563db495d7a9f40cc90d79a8568cb5eb9b7a2692a7b26b153` | units pass; 101/1669 host64 hits: reject |
| 2 frames / 6 symbols | `/var/tmp/leo-host-sparse-proposal-26-v2` | `c71d1d59f0a7e2d44ece2917ce5d9fc07f4db8b1297170be8d50009cfaada7a8` | units pass; 403/1669 host64 hits: reject |
| 4 frames / 12 symbols | `/var/tmp/leo-host-sparse-proposal-412-v2` | `3d71b2ebb0268850d0c595bff20e52ec8214f22517ea913976c0034b2d01fa8d` | units pass; 1036/1669 host64 hits: reject at 32 centers |
| 16 frames / 12 symbols | `/var/tmp/leo-host-sparse-proposal-full-v2` | `6e792e83b7ecaa8f4b85251e7d96a90eccaa5fb467d26ad97236048cce91a561` | byte-exact unit; host64 11264 objects and 1669 hits exact |
| 1/3 ASAN/UBSAN | `/var/tmp/leo-host-sparse-proposal-13-asan-v2` | `2bb746a2a6e6f27481c7a78085bf20b5a7ef49ba6eb0f917a704367c414f998f` | all units pass |
| 4/12, 128 centers | `/var/tmp/leo-host-sparse-proposal-412-c128-v1` | `f7b991b24e72a81b3a9251d9b8d34b76039f164c86e2661cd4a6afd78d398fa5` | mixed 1247/1669; 2.5M 388/485: reject mixed gate |
| 8/12, 128 centers | `/var/tmp/leo-host-sparse-proposal-812-c128-v1` | `6ed5c4195c86d14e304568210da302f6f97a83f444e47729e7a06a8abbd9f6e6` | mixed 1521/1669; 2.5M 454/485: passes host64 gates |
| ARM 4/12, 128 centers | `/var/tmp/leo-arm-sparse-proposal-412-c128-v1` | `c9f23c369186363ce2fcbf7972caa18d53385ffe413c9447afc5fdf61c8a0e34` | cross-build only |
| ARM 8/12, 128 centers | `/var/tmp/leo-arm-sparse-proposal-812-c128-v1` | `bbc758d3b5e2fe9890d4b67e3972aaaa93e196effcea177b9632a341356bbe79` | cross-build only |

Exact source snapshots and receipts are archived under `builds/`. ARM builds
for the two 128-center follow-ups are archived after host64 selection. Both
ARM all-rate units pass on CPU0. The completed host704 results and bounded
ARM saved-IQ measurements are documented in REPORT.md.

The 32-center host64 screens all fail the 80% recovery gate. Follow-up host
builds widen only the center count: 4/12 with 128 centers is at
`/var/tmp/leo-host-sparse-proposal-412-c128-v1`, and 8/12 with 128 centers is
at `/var/tmp/leo-host-sparse-proposal-812-c128-v1`. Both pass the same units.
The 8/12 build passes the host64 gate with 91.13% mixed-rate and 93.61% 2.5-MS/s
hit recovery; 4/12 reaches only 74.72% mixed-rate despite exactly 80% at 2.5
MS/s.
