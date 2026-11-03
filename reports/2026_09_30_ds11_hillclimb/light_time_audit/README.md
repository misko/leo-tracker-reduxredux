# Signal travel time is predominantly a constant CFO correction

The classical retarded geometric Doppler audit completes on all 120 retained
tracks from scans 0 and 16. Median absolute corrections are 6.42 and 6.48Hz
over all candidate/observation rows. Once centered using each candidate's
training-row mean, maximum absolute corrections are only 0.0102 and 0.0124Hz.
For the original training-MAP candidates the maxima are 0.00464 and 0.00472Hz.
Light times range from 1.16 to 3.47ms in these banks.

The original model profiles a separate constant CFO per track and candidate.
It can absorb almost all this correction, subject to its weak CFO prior. This
measurement therefore deprioritizes omitted geometric travel time as an
explanation for the observed hundred-Hz residual structure. No position fits
are launched and no position-error bound is inferred from the small shape
change alone.

The audit iterates geometric range/c, approximates emission states using local
quadratic ECEF motion, rotates emission coordinates into reception ECEF, and
analytically differentiates the implicit range equation. The coordinate
convention follows [ESA Navipedia](https://gssc.esa.int/navipedia/index.php/Satellite_Coordinates_Computation).
The rate formula is our derivation. This is not a complete relativistic,
atmospheric or satellite-clock model, nor an absolute ephemeris validation.
Bank interpolation and local acceleration approximations remain limitations.

Two tests pass: exact constant radial motion, and differentiation of the
implicit range under quadratic motion and Earth rotation, including static
ECEF zero rate. All persisted source hashes verify. Original causal banks,
observations and training-selected baseline positions remain unchanged; the
geographic reference is never used.

See [protocol](PROTOCOL.md), [implementation](core.py), and
[complete quantiles and per-track shape RMS](outcome.json).
