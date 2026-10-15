# A029 widened endpoint: gradient is real near objective resolution

The corrected zero-fit audit completed **9 objective evaluations and 9 geometry checks in 15.038 s**, with all nine input/result pairs saved before final serialization. No optimizer, held-data, or reference access occurred. The strongest projected gradient is coordinate 7, the common satellite time shift. Its independent KKT remains **0.003188312**, so the endpoint stays excluded.

| Coordinate | Scaled analytic gradient | FD at scaled 1e−5 / 1e−6 | Gradient curvature | Predicted coordinate decrease / objective ULP |
|---|---:|---:|---:|---:|
| Common time, 7 | 0.003188312 | 0.003193418 / 0.003181412 | 934890.556 | 5.437e−12 / **1.494 ULP** |
| Common-clock nuisance, 47 | 0.000025297 | 0.000025648 / 0.000025466 | 4.975 | 6.431e−11 / **17.678 ULP** |

Objective ULP is 3.637978807e−12. Both FD scales confirm a real gradient rather than a spurious analytic derivative. No hard visibility or soft-support memberships change. The larger common-time stencil crosses five interpolation cells, while the smaller stencil crosses none; both yield essentially the same curvature. The geometry and gradient evidence supports a numerical stopping problem near objective resolution. A coordinate decrement estimate is not a coupled Hessian, minimum certificate, proof of a unique cause, or authorization to relax KKT.

The largest centrally feasible physical and nuisance coordinates were selected by training gradients, and the direction plan was written before probes. All perturbations remain feasible under the same original global prior, widened local disk, timing, physical, and nuisance bounds. No initializer or probe was clipped. The full projected gradient and active-box inventory are preserved; the selected physical coordinate is also the full projected maximum.

The original audit version (`3f6c9e61f`) failed **after computing nine objectives/nine geometry checks**, while constructing the final result with duplicate `optimizer_calls` keyword arguments. Its failure namespace and saved direction plan remain unchanged; its numeric probe results were not persisted and are unavailable. One explicitly authorized new v2 repeat was run after four tests passed, including a real soft-model public lifecycle test without serialization mocks and a postcheck-failure test proving all nine scientific receipts survive. **Total consumed audit cost is 18 objectives/18 geometry checks, not nine.** No fit was repeated by these diagnostics.

Successful source `ed2114f19`; authority `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-detectability-wide-roundoff-029-v2`. The adjacent JSON binds protocol, launch, direction plan, result, seal and termination; the scientific seal includes all eighteen per-call input/result receipts. The accepted original-domain A029 result stays 39.987144 km, the wider-domain selector remains unavailable, and the separate A071 contrast pilot remains 0.195307 km. No cohort result is substituted.
