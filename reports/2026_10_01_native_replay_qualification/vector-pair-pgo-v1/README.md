# Optional vector pair-bound qualification

The research scorer packs endpoint orbit states and evaluates four conservative
Doppler intervals with NEON. It only rejects candidates whose intervals prove
they cannot beat the incumbent. Uncertain lanes retain the existing double
precision subset/full scoring. Final scoring and public contracts are unchanged.
Enable explicitly with `LEO_RESEARCH_VECTOR_PAIR_BOUND`; scalar remains default.

The endpoint-bank capacity grows from 32 to 64 MiB per context in this mode.
The preceding matched ordinary-build experiment (`../vector-pair-bound-v1/`)
saved 4.03% CPU on 16 held-out sites, with exact scores, while process RSS grew
from 77,588 to about 116,952 KiB. That experiment alone does not qualify a full
search or concurrent acquisition.

Physical ARM training uses only the four sites from
`../score-pgo-immutable-arm-v1/training.tsv`, with the unchanged fresh-track LOC1
input. The profile and source hashes are retained here. Generate and use builds:

```sh
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_arm_score_pgo.sh generate /var/tmp/leo-modular-location-arm /var/tmp/leo-vector-pair-pgo-v1 immutable vector
# Train instrumented bench-search-sites on PLUTO+ with GCOV_PREFIX_STRIP=3;
# retrieve score.gcda into the identical build directory before the use build.
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_arm_score_pgo.sh use /var/tmp/leo-modular-location-arm /var/tmp/leo-vector-pair-pgo-v1 immutable vector
```

The recipe validates source hashes, immutable-session mode and vector mode
before consuming the physical profile. Tests cover mismatched profiles and
invalid mode combinations. Portable interval and recipe tests: 5 passed.
The updated host interval test also passed AddressSanitizer/UndefinedBehaviorSanitizer:
327,988 valid intervals, 265,648 scalar and 759,704 vector rejection checks,
worst error/enclosure ratio 0.115446. This is sampled validation, not a proof
over every floating-point input.

Full physical results are saved separately in `../regional-arm-vector-pair-v1/`.
Search completed in 142.216759 wall / 270.442212 CPU seconds, with 120,772 KiB
peak RSS, versus 158.115778 wall / 297.358715 CPU seconds for the qualified
scalar build. CPU savings are 9.05%; wall savings are 10.05%. The full 400-point
search JSON and selected full associations are exactly equal to the previous
ARM results. Independent host search differs by at most 5.69e-13 Hz, below the
predeclared 1e-9 Hz tolerance; selected associations match host JSON exactly.
Final association scoring took 2.355866 wall / 3.595210 CPU seconds, so that
stage is slightly slower. Physical location, stencil and immutable-session
unit tests passed. These isolated timings do not establish concurrent cadence.
The 400-point budget and 250 km prior stay unchanged. Budget exhaustion must
not be interpreted as global convergence. Concurrent original-cadence replay
remains a separate required qualification.
