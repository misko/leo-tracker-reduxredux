# Complete cold-fit bounds and certified Schur conditioning

The valid complete-fit loss floor ranked out **zero of seven dense hypotheses** and **zero of two weak hypotheses**. A separate native certificate bypassed **3,197 of 4,098** ordinary conditioning estimates on dense DS30-0008, with identical completed science. The matched ordinary C clock fell **81.5 ms**. The certificate bypassed none of the dense grid estimates. The evidence does not establish the 0.5-second attributable gain required for integration. [Frozen protocol](conditioned-factor-protocol.md) · [Reconciled paired receipts](measurements/conditioned-factor.json)

## Bound on a complete hypothesis

The actual cold ranking fixes a satellite and signed integer alias per track of each hypothesis. The optimizer compares the squared norm of its residual vector, including the fixed diagonal noise volume and the below-horizon penalty. The reported negative twice ELBO also contains a normalization constant. The cold race compares the fit's residual score and omits that constant. Motion of the trial position and the next absolute phase linearization can change the Doppler intercept and design simultaneously. The fitted receiver nuisance coefficients and Gamma rates also depend on all retained rows. A partial innovation sum at a particular trial therefore bounds only that returned trial with its fitted coefficients and weights. It supplies no bound on the score after the candidate moves or refreshes. [Finalist scoring](cold_finalist_race.py) · [Position residual](../../../src/leo/analysis/localization_v3/position.py) · [Native and fallback objective](../../../src/leo/analysis/localization_v3/hierarchical.py)

For a fixed energy \(E_g\) of normalized innovations evaluated at given nuisance coefficients, the rate-dependent innovation and Gamma squares of a group with power \(p_g\) and fixed shape \(\alpha_g\) minimize to \(2\alpha_g\log(1+p_g E_g/(2\beta_0))\). A stronger complete-fit lower bound could use a certified lower bound for \(E_g\) over all remaining positions, phase references and nuisance coefficients. Clipping the phase refresh to ±15 s constrains the expansion point and still leaves the Gaussian coefficient support unrestricted. Previously measured common receiver offsets connect the dense candidate across tracks. A group energy computed at a frozen posterior or a per-edge filter therefore does not supply the missing global relaxation. [Coupled assignments](assignment-components.md) · [Common-position likelihood operands](dense-assignment-reuse.md) · [Earlier Doppler-change proposals](arc-doppler-start.md) · [Proof-owner reduction](proof-global-rank.md)

The fixed term \(2\sum_i \log(\sigma_i/40)\) is present at every trial and refresh with unchanged volume and retained observations. The audit took an outward-rounded floor of that term and left all other nonnegative contributions free. It compared the floor for every observed fully assigned branch against the completed incumbent on the actual cold route.

| Saved input | Complete assignments / finalists | Rows per assignment | Valid score floor | Completed incumbent | Ruled out |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense DS30-0008 | 7 / 3 | 4,896 | 12,244.8996 | 36,359.3075 | 0 |
| Weak DS30-0016 | 2 / 2 | 132 | 307.5641 | 770.9521 | 0 |

Every branch within a recording had the same floor. The dense route retained the installed heuristic prefix race, which completed one branch. Both weak finalists completed. No measured decision uses the new floor. [Dense audit](measurements/conditioned-factor-dense-stock.json.gz) · [Weak audit](measurements/conditioned-factor-weak-stock.json.gz)

## Conditioning certificate in the complete solve

A prior dense likelihood witness spent **39.9 ms of 107.6 ms** in the LAPACK calls for one 256-update fit. The tested shortcut targets only their repeated Schur reciprocal-condition estimate. On the rounded lower factor \(L\) returned by Cholesky, form a triangular comparison matrix with the same positive diagonal and off-diagonal entries \(-|L_{ij}|\). Solving this comparison system against ones majorizes the absolute row sums of \(L^{-1}\) by induction. For the vector of majorants \(w\), the upper bound \(\sqrt n\sum_i w_i^2\) encloses \(\|(LL^T)^{-1}\|_1\) in exact arithmetic. The code pads the positive accumulation, uses the same Schur 1-norm as the released estimator and requires a factor-of-eight margin above its threshold. An inconclusive calculation falls back to the original estimator. The original Cholesky, solve, covariance inverse, complete block inverse condition check and update stopping rules remain active. [Native code](conditioned_factor.inc) · [Original profile](../single-core-2x/solver-wide-private-blocks.md)

| Same saved input and arithmetic outputs | Dense stock → certificate | Weak stock → certificate |
| --- | ---: | ---: |
| Ordinary native CPU | 1.813 → 1.731 s | 8.49 → 6.89 ms |
| Checked grid native CPU | 2.055 → 1.968 s | 27.02 → 20.24 ms |
| Estimator calls bypassed, ordinary | 3,197 / 4,098 | 912 / 912 |
| Estimator calls bypassed, checked grid | 0 / 5,834 | 3,317 / 3,317 |
| Full saved solve CPU | 24.069 → 23.373 s | 2.640 → 2.622 s |
| Full saved solve elapsed | 28.024 → 23.394 s | 2.653 → 2.635 s |

The dense grid attempted the comparison and still called every original estimator. Its observed **86.9 ms CPU difference** favors the candidate by a similar margin to the ordinary boundary that actually skipped calls. The dense complete-solve difference of 0.697 CPU seconds therefore includes variation beyond the measured shortcut. On the weak recording, the two compiled native boundaries together saved **8.38 ms**. These are single pairs in opposite arm orders. The same-recording approach passed the science checks and leaves performance evidence below the integration threshold. [Exact comparisons, native channels and timing](measurements/conditioned-factor.json)

Both arms matched their original endpoint and RF output, owner hashes and recorded rows, path and numerical grid digests, and zero endpoint replay. The complete regional proof, selected cold branch, 356 checked grid exports per packet and original native and fallback counts all matched. Fixed-zero / fitted RF RMS remained **140.961 / 140.950 Hz dense** and **121.526 / 120.291 Hz weak**. No raw acquisition or rendering ran. No geographic reference was loaded to choose the solver path. [Dense certificate](measurements/conditioned-factor-dense-certificate.json.gz) · [Weak certificate](measurements/conditioned-factor-weak-certificate.json.gz)

## Reproduce

Run `conditioned_factor_trial.py CASE MODE NEW_DIRECTORY` with the installed Gauss payload and release Python. Use the existing shared lock on CPU 2 with nice 15, best-effort I/O priority 7, one numeric thread and a fresh tmpfs directory writable by the archive-readable `leo` account. Run dense stock then certificate, and weak certificate then stock. The runner authenticates the saved genuine short packet, supplied offer and TLE archive, and invokes the same full numerical solve as the published control. Run `conditioned_factor_score.py RUN_ROOT NEW_SCORE.json` to recheck the pair. The gzip artifacts decompress to the original sealed receipts. Timing fields are excluded by name from the exact scientific comparison, while diagnostic call counts and solver data remain compared.

Three exploratory starts stopped before completing a fix. The pinned regional library needed the archive-readable process, the diagnostic wrapper needed to expose the existing ctypes ABI metadata, and the cold observer needed to skip exploratory proposals with no explicit signed alias. The final saved runs contain those corrections. Nineteen component and adjacent tests passed. [Runner](conditioned_factor_trial.py) · [Scorer](conditioned_factor_score.py) · [Component tests](../../../tests/pipeline_eval/test_conditioned_factor.py)
