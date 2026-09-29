# Wave 8 primary-rate gate frontier

This bounded sweep raises only the 2.5 MS/s coarse threshold in the Wave 8
exact-rank frontier source.  All 22 windows, other rate thresholds, proposal
geometry, and final FP64 scoring remain unchanged.  It is an additional
quality tradeoff, not an exact optimization.

The frozen Host704 control at threshold 0.312 recovers 4,235/4,573 primary-rate
standard hits and 18,465/19,581 overall.  The required primary floor was
4,116/4,573 (90%).

| 2.5 MS/s gate | Primary recovery | All-rate recovery | Emitted objects | Host outer ms/dwell | Pass floor |
|---:|---:|---:|---:|---:|:---:|
| 0.313 | 4,230/4,573 | 18,460/19,581 | 77,620 | 58.266 | Yes |
| 0.3135 | 4,223/4,573 | 18,453/19,581 | 77,512 | 57.171 | Yes |
| 0.314 | 4,211/4,573 | 18,441/19,581 | 77,383 | 53.977 | Yes |
| 0.320 | 3,717/4,573 | 17,947/19,581 | 76,270 | 58.810 | No |
| 0.325 | 3,117/4,573 | 17,347/19,581 | 75,591 | 59.441 | No |
| 0.330 | 2,611/4,573 | 16,841/19,581 | 75,063 | 57.610 | No |

The finer sweep shows that 0.314 is the highest tested gate above the floor. It
retains 4,211 primary hits and emits 4,952 primary-rate candidates, 511 fewer
than the 0.312 control's 5,463 (9.35%).  It was cross-compiled as the sole ARM
candidate. The non-PGO ARM4 run measured **474.694325 ms/dwell**, recovering
**107/119** original hits (89.92%); this small panel is below the 90% recovery
floor despite the larger host panel passing it. Host runtime is noisy and does
not establish the target saving. This calibration uses the DS7 Host704
panel.  Although the PGO held-out32 timing panel excludes its four training
contexts, it is not unseen with respect to this DS7 gate calibration.
`results.json` binds every cohort, receipt, audit, and row stream.

Additional complete host checks recover **745/785** DS8 hits and **861/908**
DS9 hits, each over 32 dwells and 704 windows. The valid DS8 run is
`host-ds8-314-retry`; its predecessor stopped after a temporary-filesystem
write failure and is not qualification evidence. These are scientific transfer
checks, not ARM runtime measurements.
