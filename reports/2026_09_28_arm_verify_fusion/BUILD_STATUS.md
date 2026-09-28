# Build status

All builds are isolated from the screen-rotation V1 baseline and contain
source hashes, compiler commands, and binary hashes in `build.json`.

| Build | Path | Receipt SHA-256 | Local status |
| --- | --- | --- | --- |
| Host | `/var/tmp/leo-host-verify-fusion-v1` | `90d145f00129d9e8529a20b386b8b3d3da5ac40a168b8d19ed1ea660fed42573` | all three units pass |
| Host ASAN/UBSAN | `/var/tmp/leo-host-verify-fusion-asan-v1` | `d59c1cad3144c7d9eb19e773415b4f90516f8a2f2541635b11acc9c2f49fb0ca` | all three units pass |
| ARM | `/var/tmp/leo-arm-verify-fusion-v1` | `0adfc53146e9bf3467415f58b7b91c54c54ca29eef563bc1ffb138f6d930f1d8` | hardware-owner unit passes |

The verification-specific unit requires exact equality with the three
original normalized scores. It passes at every supported rate for randomized
full and partial inputs and zero samples. No performance result is included.

The bounded host64 paired audit also matches all 11,264 candidate objects,
1,669 positive hits, and 691 positive windows with no added hit. This is
candidate-parity evidence, not a performance result.

The preliminary four-probe ARM comparison is candidate-identical and measures
1532.124643 ms versus 1542.867175 ms for screen-rotation V1 (1.0070115x).
Full-cohort acceptance completed: the ARM 88-window run matches all 704
candidate objects and 119 hits, averaging 33.728123 s/dwell versus 33.912983 s.
The host704 run matches all 123,904 candidate objects, 19,581 hits, and 7,007
positive windows. See PERFORMANCE_REPORT.md and the paired audit receipts.
