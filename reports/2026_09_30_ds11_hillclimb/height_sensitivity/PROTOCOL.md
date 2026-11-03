# Unknown-height sensitivity at the original fitted geometry

Scans 0 and 16, unchanged causal banks, original training-selected endpoints.
Condition on each track's original training-MAP satellite; do not claim decoded
identity. Evaluate Doppler derivatives in E/N km, timing seconds, and receiver
ellipsoidal height km. Height moves the receiver along the ellipsoid normal.
Compare central differences with 1m and 10m steps. Horizontal/time derivatives
use the original steps 1e-4km and 1e-5s. Profile a constant per track by weighted
centering. Report equal weights and positive Student-t IRLS weights from the
original training residuals. Neither is the full observed mixture Hessian.

Project height derivative on horizontal/time derivatives. The coefficients
describe local aliasing if true height changes while fitted height stays zero,
not an estimated altitude, corrected location or geographic accuracy bound.
Report horizontal alias per hypothetical 100m height and remaining conditional
height information fraction. No reference coordinates, height tuning, new orbit
data, optimizer or accuracy comparison. Bind the metadata's explicit unknown
altitude but do not infer a value from its horizontal reference coordinates.
