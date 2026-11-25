# DS30-0218 held position replay

The frozen masked CFO correction improved position by **237.39 m with
`c=0` and 251.22 m with fitted `c`** compared with the ordinary successor
on the identical authenticated saved packet. Both corrected errors also
beat the installed original-input positions on this recording. DS30-0218
was the prospectively enrolled 65th execution case. This is one held
physical recording and the correction was measured at the saved position
boundary. [Frozen enrollment](masked-cfo-next-original.md) ·
[Verified position score](measurements/masked-cfo-0218-prospective-score.json)

| Position publication | Fixed `c=0` error | Fitted `c` error | Fixed conditional RF RMS | Fitted conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Installed original 20 ms | 883.12 m | 952.96 m | 109.73 Hz | 109.77 Hz |
| Ordinary successor 20/8 ms | 1,056.80 m | 1,124.69 m | 139.91 Hz | 139.84 Hz |
| Corrected successor saved replay | 819.41 m | 873.47 m | 135.96 Hz | 136.00 Hz |

Both saved cells exited zero with both calibration arms, standard
179-point grid, position path and eight verified PNGs. The ordinary
cell exactly reproduced the official raw successor's terminal, ordered
owners, grid, path, figures, Graph counters and source. The corrected
cell applied 530 nonzero edits among 6,479 winners before rebuilding the
ordinary Graph. Graph support moved from 4,974 rows and 155 tracks to
5,007 rows and 159 tracks. Both chose `lean` from healthy sample evidence,
ran one inference, accepted the named final fit and saved one regional
handoff. The late boundary check reported no exterior evaluation in
either cell. Both cold passes recorded an ambiguous gap, with selected
branch labels 1 and 2 respectively. The two final fits carry their own
selected supports. [Closure digests](measurements/masked-cfo-0218-prospective-closure.json)

## Signed RF diagnosis

The offline readback recovered all 530 exact edits after both
publications sealed. Holding the ordinary predictor, alias and ownership
fixed, 442 edited owners drove the signed RF reduction in both arms.
The other 3,585 ordinary owners were unchanged in that fixed-state
calculation. Each number below uses the indicated paired population.

| Matched population | Owners per arm | Fixed `c=0` RMS | Fitted `c` RMS |
| --- | ---: | ---: | ---: |
| Ordinary owners, fixed predictor | 4,027 | 154.71 → 150.71 Hz | 153.20 → 149.21 Hz |
| Edited ordinary owners, fixed predictor | 442 | 140.62 → 93.05 Hz | 141.61 → 95.18 Hz |
| Common owners, actual rebuilt predictions | 3,745 | 151.56 → 148.69 Hz | 149.03 → 145.18 Hz |

Rebuilt ownership retained 3,745 common rows, removed 282 and added
190, leaving 3,935 corrected owners per arm. None of the common owners
changed NORAD. Of those, 98 moved from conditional to predictive. The
matched residual improvements and changed branch, roles and roster show
both the direct CFO effect and subsequent changes in the fitted model.
The fixed-state scalar readback does not isolate a geographic effect.
[Verified fixed-residual score](measurements/masked-cfo-0218-prospective-fixed-residuals.json)

## Timing and custody

| Saved cell | Namespace launch through exit | Worker to verified publication, wall | Worker to verified publication, CPU | Post-closure residual export, wall |
| --- | ---: | ---: | ---: | ---: |
| Ordinary | 22.876 s | 22.400 s | 21.584 s | 0.043 s |
| Corrected | 23.521 s | 23.118 s | 22.712 s | 0.037 s |

Feature derivation used 0.756 s wall and 0.755 s CPU of the corrected
worker. The offline fixed-residual readback took 1.227 s wall and
0.946 s CPU on CPU3. The namespace launcher returned only the direct
wrapper CPU counters. Complete-worker CPU through exit is unavailable.
The table's CPU measurements come from the worker's in-process clock at
verified publication.

The separate official original-input process clocks were 121.142 s wall
and 108.176 s CPU for installed, and 66.559 s wall and 61.198 s CPU for
the unmodified successor. Including common publication verification they
were 121.683 s wall and 108.715 s CPU, and 67.120 s wall and 61.757 s CPU,
respectively. The correction has no measured raw-to-exit timing.

Both official rows first verified against pair
`e1571bbddaf4b47d6bc87a59613a92744689b83bd7608ceff3f74683b64d15ce`.
All 50 source-pinned TLE bodies were hashed and hard-linked within tmpfs.
The signed cutoff and archive digest match the independent custody audit.
An initial metadata-only staging invocation under isolated Python
failed to find the `leo` package before creating a stage. Explicitly
adding the pinned release `src` directory to its metadata import path
resolved the issue. Both real no-solve capsule preflights then passed at
readiness SHA-256 `9af901d1330def3b73832b024ed8f985d6277369a74caac720505024fa8fe2f0`.

The ordinary and corrected cells used separate fresh official storage
deferrals under the same single CPU2 lease, both within the 24-second
cap. Ordinary parity sealed at
`2fb22713ae14fdc5a995ea1bb6492569da09b94597a03c07dab145358f0f2806`
before the correction launched. Orbit and native data were read from the
sealed RAM-only stage. The held survey joined only after both clocks and
scientific publications sealed. Full saved artifact and image roots are
available under `/dev/shm/leo-v3-0218-prospective01`.
[Coordinator](masked-cfo-0218-capsule.md)
