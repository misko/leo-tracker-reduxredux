# C053 geographic disk expansion improves 10.056 km to 1.749 km

A matched 25 km versus 50 km local-disk experiment reduced the clock-enabled C053 selected error from 10.055802 to 1.749188 km. Both fits passed the unchanged convergence and independent objective/NLL/KKT checks. The expanded fit stopped 36.214780 km from the unchanged original center, inside its 50 km disk.

| Local radius | Objective | NLL | Stationarity | Endpoint radius km | Error km |
|---|---:|---:|---:|---:|---:|
| 25 km | 23693.894241 | 23351.163301 | 0.000097697 | 25.000000 | 10.055802 |
| 50 km | 22885.711905 | 22639.385952 | 0.000168314 | 36.214780 | 1.749188 |

The training-selected source endpoint was on its original geographic boundary. Its radial outward derivative was −38.549343 objective units/km, independently checked by a ±0.001 km finite difference of −38.549410. A 0.001 km outward step lowered the objective by 0.034786. This reference-free trigger admitted expansion before either new fit or any reference join. A fixed-nuisance 1 km outward step instead worsened the objective by 2588.141, demonstrating why full parameter reoptimization was needed; there was no reference-selected direction or relocation of the center.

The same saved vector and nuisance values seeded both arms. Candidate bank, receiver lifts, clock/group priors, observations, satellite timing constraints and 20-second/600-iteration fit budgets were unchanged. The original accepted endpoint remained eligible in both arms. The 25 km fit used 558 evaluations/20.047 seconds; the 50 km fit used 445 evaluations/15.142 seconds. The complete bounded experiment took 46.239 seconds, with four radial screening evaluations, one pre-fit source audit, two optimizer calls and independent final audits.

This separates two mechanisms in the C053 prototype sequence: receiver-clock flexibility changed selection from the distant region (253.902 km error) to the closer region (10.056 km), then geographic expansion allowed refinement to 1.749 km. It is not yet sub-kilometer performance. The earlier conditional half-band fits used 25 km disks, so comparing this expanded result with their errors would confound domain size. Matched expanded-domain low/high fits are required next. No full-cohort estimator is promoted.

The test suite covers actual native radial derivative agreement, identical seeds/centers and equal budgets across radii, retained incumbent on rejected fits, no retry, and blocked reference evaluation before sealing. Two component tests and Ruff passed. Source `62c21e32d`; evaluator `ad91239a6`.

Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-disk-053-v1/`. Terminal SHA256 `6f90f38f3048ab0ff1eb6f34f1f539e4e7e74b81f3aa7b12497ff1b87cd1e882`; seal SHA256 `46b3807c460a4e7d77809893b45fe0b5cd688a68e9e32b5f5c36e24b6b1062bf`. Reference coordinates were joined only after both outcomes and selections were sealed.
