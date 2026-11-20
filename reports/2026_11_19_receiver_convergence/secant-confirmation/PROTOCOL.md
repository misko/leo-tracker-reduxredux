# Bounded secant fit on eight confirmation recordings

Use the exact sealed `v5_secant_fit` from the six-case position-fit study.
Retain the original phase-refresh policy, complete recorded native GLRT
detections, original 25 km tile, causal catalogue, branches, both calibration
arms and full compact v5 cavity decision. The six timing pairs form a separate
cohort.

Select the first four DS26 IDs in the phase confirmation's frozen hash
order and the first four DS29 IDs in its sorted order. The order below depends
only on that earlier roster. No positions or runtimes enter the choice.

1. DS26-0142
2. DS26-0223
3. DS26-0301
4. DS26-0018
5. DS29-0127
6. DS29-0316
7. DS29-0357
8. DS29-0519

Use the standard `v5_secant_fit` runner on CPUs 16–19, with four workers at
most and a 480 s deadline per attempt. Keep all failures, withholdings and
elapsed times. Use the authenticated compact projector archive and the four
original v5 options as position controls. Their native, catalogue, request and
tile bindings must match the confirmation inputs. Seal secant and stock
positions before opening geographic references. Report each calibration arm's
coverage, geodesic errors, paired error differences and conditional RF RMS.
Confirmation stock times are historical. The six separate fresh timing pairs
supply matched wall-clock comparisons. No RF is collected.
