# Live portable verifier integration

The original scanner ran the C verifier on **28 antenna evaluations per portable arm**, covering 12 held signed stereo visits from three installed producers. Those evaluations included four peer retries selected by the unchanged scanner logic, and 224 candidates per arm. Every real coarse seed and fine grid matched the corresponding live control in order. The native batches preserved the full public, per-probe and downstream native candidate order, fields and gates within the declared tolerances. All 12 installed native packets also matched their independent stored archive exactly. [Manifest](manifest.json) · [Protocol](PROTOCOL.md)

The held set included rejected, dilute single-positive, equivalent-candidate and stronger stereo visits from each recording. All offered evaluations used the C path. The recorded maximum changes across the portable packets were **1.44 × 10⁻¹³** in fractional margin, **1.30 × 10⁻¹² sample** in fractional epoch offset and **1.17 × 10⁻¹⁰ Hz** in fractional tracking CFO. Equivalent-candidate flags appeared on 26 candidates per arm. The complete ordered traces preserve the exact floating-point differences and distinguish them from gate or rank discrepancies.

## Full resident detector cost

| Recording | Installed CPU | Portable on installed coarse CPU | Prepared CPU | Portable on prepared coarse CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 3,197 ms | 2,529 ms | 596 ms | 466 ms |
| DS29-0082 | 2,248 ms | 1,823 ms | 477 ms | 426 ms |
| DS29-0519 | 1,332 ms | 847 ms | 583 ms | 337 ms |

The values are median warm process CPU per stereo visit from three repetitions per visit and arm. Portable verification reduced median CPU by 19–36% with installed coarse and 11–42% with prepared coarse. The prepared-coarse portable arm measured 339–557 ms warm elapsed time and 147–149 MiB peak process RSS. Its route setup took 27.5–30.3 ms wall time within the loaded producer. Arm order rotated across recordings, and each arm ran in its own process on the same assigned host core for that recording. Signed CI16 authentication and preload preceded detector timing. [Stage figure](verifier-integration-stage.pdf) · [Timing CSV](stage.csv)

## Runtime boundary

The sandbox binds the corresponding installed producer’s coarse-stage source and keeps its live grid, selector and refinement of the coarse epoch. Once the original scanner offers an antenna, the port passes that antenna’s genuine seed group and bound CI16 to the existing native verifier in one call. The worker creates its exact and rolled template context once and reuses it throughout the run. The portable arm used 26 CI16 lane loads for its 28 evaluations. Coarse computation remained the largest measured stage. In the audited prepared-coarse calls, coarse CPU averaged 269–374 ms per visit and the native verifier averaged 129–140 ms.

The C route performs fine and conditioned CFO, held-pilot ranking and integer and fractional GLRT. Python and NumPy remain in the installed coarse path, template provisioning, original scanner scheduling and public/native projection. The port uses the same production packet constructors and threshold comparisons. The 54,624-byte verifier shared object links `libm` and `libc`, and its reusable numerical context is 5,858,144 bytes. Geometry and sensitivity guards route back to the original post-coarse implementation. This study measures the normal detector on a bounded resident host sample. Recorded-clock throughput, target-board speed and positioning remain outside the measured scope.
