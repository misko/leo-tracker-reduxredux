# Signed CFO and noise weighting explain the mixed DS30-0016 sensitivity

Restoring only signed CFO on 306 close short matches lowered the fitted horizontal error from **1.694 to 1.533 km**, recovering **161 m** of the **235 m** gained by restoring the complete stock tuples. The remaining **74 m** coincided with the installed radio noise model switching from constant variance to margin-dependent variance. The original mixed membership remains fixed at 475. All three results have the same 116 ordered observation, satellite and role rows per calibration arm. [Protocol](full-short-cfo-only-protocol.md) · [Receipt](measurements/full-short-cfo-only.json.gz) · [Earlier complete-tuple crossover](full-short-factor-contrast.md)

| Same mixed membership | Fixed / fitted horizontal error (km) | Fixed / fitted RF RMS (Hz) |
|---|---:|---:|
| Original archived mixed | 1.311046 / 1.694025 | 121.526246 / 120.290865 |
| Synthetic CFO restoration | 1.234661 / 1.533101 | 120.946602 / 120.447514 |
| Archived complete-tuple restoration | 1.159880 / 1.459032 | 121.024858 / 120.517558 |

The synthetic CFO replacement recovers **76 m fixed and 161 m fitted**, about **51% and 68%** of the complete-tuple improvements. Relative to the original mixed finish, RF RMS falls by **0.580 Hz** in the fixed arm and rises by **0.157 Hz** in the fitted arm. Compared with the complete-tuple restoration, it leaves **75 m fixed and 74 m fitted** additional survey error. Frequency fit and position separate even on an exact common owner roster.

## The parameter and the noise decision

The unchanged signed join identifies 207 RX0 and 99 RX1 nonanchor measurements within two wrapped samples and 250 Hz of their named counterparts. The diagnostic replaces only `fractional_tracking_cfo_hz` in those 306 short tuples. It keeps the previously chosen epoch, fractional offset, rank, exact and rolled scores, acceptance and margin, and retains every other mixed row byte-for-byte under canonical serialization. It has its own analysis and recipe digest, with no claim that the mixed receiver measured those hybrid tuples.

The installed `winning_observations` adapter reads one frequency field and derives observation time from the lane hardware counter. It uses fractional epoch to validate and distinguish candidates inside a probe. The enrolled observations carry one accepted candidate at most. At that cardinality, epoch and rank do not change the installed graph or likelihood inputs. The adapter carries the observed fractional margin into `estimate_noise`, whose model is selected by the sign of its BIC gain.

A separate replay of only the installed Graph and radio noise estimate reproduced the CFO-only run's actual noise diagnostics exactly. The CFO-only and complete-tuple inputs produce the same complete track digest, with 368 graph points and 14 tracks. Both fit the same 132 graph-polynomial residual samples and the same **126.034 Hz** constant sigma. The mixed margins give **−0.152897** extra BIC gain and select constant sigma. Restoring the named margins gives **+0.099768** and selects the margin-dependent per-observation scales used in curved and predictive fitting. This identifies the source of the remaining position sensitivity on this case. The narrow margins around the noise-model decision limit transfer. [Numerical and noise evidence](measurements/full-short-cfo-only.json.gz)

## Verification

One new saved solve used the installed graph and exact finish, original offer and causal archive, and the same two calibration arms. It evaluated all 179 numerical grid points, reported zero objective replay error in both arms, and emitted eight SHA- and decode-verified diagnostic PNGs with valid grid and path pointers. The solve used **3.343 CPU s** and the saved worker took **6.234 s** through exit. Its original inventory was available only as authenticated metadata and waveform reads were blocked. No raw waveform or further position solve ran. The prior reference finishes were scored from their seals. Five focused tests passed.

Use `full_short_cfo_only.py run NEW_TMPFS_ROOT` with the shared CPU 2 Gauss lock, nice 15, I/O priority 7, one numerical thread and the installed payload first in the numerical module path. Run `score` with the local scorer after sealing. `audit-noise` reads both signed derived inputs and runs only Graph and noise preparation. The numerical seal SHA-256 is `15c17790ae3da0db313a990775b59e973404577db3b51d2c73f7868fae19894b` and the graph/noise audit is `4f0e1643cd5840ce3815a8ec559bc9b77bb8d629c1e5cc35349faac040c77bfa`. [Driver](full_short_cfo_only.py) · [Tests](../../../tests/pipeline_eval/test_full_short_cfo_only.py)
