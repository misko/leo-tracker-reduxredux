# DS21-039 receiver RF score audit

The original full-view training winner has opposite receiver contributions to the shared fitted RF coefficient's score, despite a nearly zero pooled score. This is concrete model-sensitivity evidence, not a measurement of independent receiver clocks or improved position accuracy. All values below come from arithmetic on the sealed V2 calibration tables; no predictor, fit, reference join or held scoring was used. [RECEIVER_RF_SCORE_AUDIT.json](RECEIVER_RF_SCORE_AUDIT.json) binds receipts and inspected sources.

## Sampling-clock evidence

The recorded input declares one radio serial, sample rate and counter domain. The acquisition adapter receives interleaved two-receiver samples in each common counter interval. The deployed qualified preparation requests `rx_mask=3`, and the IIO adapter configures one source-locked `device.sample_rate` and matching capture rate. This establishes the configured common sampling domain. Exported metadata does not independently measure per-receiver clock ppm or attest the physical oscillator topology, nor does it establish that external RF-path clocks are shared. A common fitted `c` is an empirical model coefficient; it should not be identified with measured sampling-clock error.

## A pooled score hides opposing directions

For receiver/channel group mass \(m\), conditional wrapped residual mean \(\bar r\), and recorded RF \(f\), the saved tables suffice to recover the RF log-score:

\[
S_r=\sigma^{-2}\sum_{h\in r}m_h\bar r_h(f_h-f_0)/10^9,
\qquad \sigma=125\ \mathrm{Hz}.
\]

Positive score means a first-order log-likelihood gain for increasing that receiver's coefficient; the NLL gradient has the opposite sign. RF is constant within these channel groups. Channel/RF table matching was verified through their identical saved mass and residual means, rather than assuming channel order.

| Frozen training state | RX0 RF log-score | RX1 RF log-score | Pooled score |
|---|---:|---:|---:|
| All | +0.104227495 | −0.104227486 | +8.91e−9 |
| Low | +0.039857929 | −0.039857868 | +6.07e−8 |
| High | −0.037357860 | +0.037357829 | −3.12e−8 |

Each pooled reconstruction agrees with the actual source score recorded in the sealed receipt to within `7.6e−16`. For a contrast column with opposite signs on the two receivers, the full-view directional log-score is about `+0.208455`. The per-receiver directions are therefore not an artifact of reporting a near-zero pooled gradient.

## Band offsets and confounding remain distinct

Centering RF independently within each receiver/band using saved posterior signal masses removes constant band intercepts from this descriptive residual regression. The remaining full-view residual slopes are **+23.424 / −35.834 Hz/GHz** for RX0/RX1. Their band breakdown is:

| Frozen state/support | RX0 residual slope, Hz/GHz | RX1 residual slope, Hz/GHz |
|---|---:|---:|
| All winner, low channels | +53.480 | −50.525 |
| All winner, high channels | −14.496 | −3.756 |
| Low winner, low channels | +13.261 | −19.379 |
| High winner, high channels | −22.772 | +40.099 |

These are fixed-posterior residual trends, not estimates of calibrated hardware coefficients. Their changing signs and magnitudes across bands/views do not establish a stable receiver sampling error. The channel summaries lack RF-by-time and orbital-Jacobian crossproducts, so they cannot remove receiver drift, geography, satellite timing or assignment confounding, or establish repeated block support. Conditional design curvature would omit assignment uncertainty and is not confidence information.

The nonzero receiver contrast score supports at most a bounded, explicitly labelled RF-contrast model-sensitivity control using the unchanged native observations, bank, physical starts and fitted-`c` budgets. It does not justify a hardware correction, an external-clock prior, or another LO relabelling. No extra parameter was implemented and no control was executed in this audit.
