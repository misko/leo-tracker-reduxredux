# Independent Earth-frame replay of the recent wide solution

Replacing the research frame conversion with Astropy 8.0.1 plus the archived
IERS Earth-orientation table moves the fitted position by only **11.2–11.4 m**.
It does not explain the recent solution's multi-kilometre northward bias.

The replay retains all 622 independently assigned episodes, their 21,702
observations, randomized partitions, and the frozen quality selection. It
recomputes SGP4 input times using Astropy UTC Julian dates and converts both
TEME position and velocity into ITRS using Astropy. The archived IERS table
supplies UT1 and polar motion; automatic table downloads are disabled.
States are recomputed at UTC and ±0.5 s for the same clock-fit interpolation.
No antenna reference is supplied to this replay.

| Fit | Position movement relative to original fit (m) | Evaluation RMS change (Hz) |
|---|---:|---:|
| All, fixed clock | 11.242 | +0.000021 |
| All, shared clock | 11.394 | +0.000091 |
| Selected, fixed clock | 11.328 | +0.000083 |
| Selected, shared clock | 11.342 | +0.000102 |

The Earth-fixed satellite positions differ by a median 12.137 m and maximum
12.555 m; velocities differ by a median 0.01024 m/s and maximum 0.01439 m/s.
These include the deliberate UT1/polar-motion differences from the simpler
production numerical model. They are not evidence of an SGP4 orbit correction.

Four WGS84 checks spanning latitude, longitude, and altitude agree with Astropy's
EarthLocation to within 1.9e-9 m numerically. These test the coordinate formula,
not the survey accuracy of the antenna. The code also explicitly includes the
Earth-rotation velocity term in the original range-rate calculation.

This is an independent **frame and time-conversion** check, not an independent
orbit solution: both routes still use SGP4 and the same archived TLEs. It does
not rule out orbital-element error, erroneous RF associations, signal-frequency
measurement bias, or unmodelled transmitter/receiver behaviour. It does rule
against these tested frame approximations being the kilometres-scale fix.

The implementation follows [Astropy's satellite-coordinate workflow](https://docs.astropy.org/en/stable/coordinates/satellites.html).
The IERS file is the previously archived
[rapid-service Earth-orientation product](https://datacenter.iers.org/products/eop/rapid/standard/finals2000A.all),
SHA-256 `c672540e026d3cd4840c0858d4ce2bc4a18c3bc9751f9636c3285e11950d58a1`.
As documented in the earlier Earth-rotation audit, some dates use predictions;
this is an offline model check, not an assertion of causal online table access.

`tools/audit_wide_astropy_frames.py` accepts `--run`, `--evidence`, `--iers`, and
a fresh `--output`. [All fit results and source digests](2026_09_20_independent_frame_audit/inference.json)
are retained. Twelve tests pass, including an independent stationary-inertial
point check that Earth-fixed velocity equals the transformed position derivative,
explicit propagation-error rejection, and the existing analytic frame tests.
Astropy is a development/research dependency only; production numerical paths
and the scanner were not changed.
