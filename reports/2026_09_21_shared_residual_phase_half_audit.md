# Shared-residual audit of the dual-RX phase-half diagnostic

The two largest contiguous-symbol-half disagreements in the frozen scan-hop-6ad replay include demonstrable estimator reference failures and are not evidence by themselves of physical phase changes within a dwell. The historical offset-authority path independently estimates a pilot residual for each receiver and then branch-lifts the receiver product from their difference. In visit 1354 this introduces one 750 Hz frame alias. In visit 1428 one receiver selects the opposite 227.27 kHz pilot-symbol alias.

An explicit research estimator instead selects one within-frame residual by summed coherent magnitude across both receivers and applies that residual to both. Receiver phase is absent from this selection. It leaves the historical and published extractors unchanged.

| Visit | Historical half difference | Shared-residual half difference | Historical half frequencies (Hz) | Shared half frequencies (Hz) |
|---:|---:|---:|---:|---:|
| 1354 | 113.18° | -4.67° | -674775.06, -675526.56 | -675524.33, -675526.56 |
| 1428 | 123.08° | -20.11° | -902053.91, -675553.93 | -675554.25, -675553.92 |

All historical and shared full-window and half-window phases are transported to the historical full-window center. This exactly reproduces the earlier 113.18° and 123.08° diagnostic and persists that common time as `comparison_reference_sample`. The phase-blind pair is the sole pair returned for each visit, and its common applied seed reference is persisted as `common_reference_sample`.

This improvement does not identify an absolute full-window phase. At the common historical centers, the shared-residual full-window phase shifts by +7.01° in visit 1354 and +16.96° in visit 1428. The raw phases at their own different weighted centers differ much more because a few samples at roughly 675 kHz rotate phase substantially; those values are persisted but are not compared directly. Frequency changes are 0.04 and 0.11 Hz, resultants change from 0.99093 to 0.99091 and from 0.94989 to 0.95231, and exact-to-control floors change from 18.42 to 18.34 and from 22.71 to 21.28. The selected common residuals are 111760.18 and 112845.03 Hz. The remaining common-time shifts with unchanged conventional quality metrics show that the opt-in estimator is a bounded diagnostic, not a replacement phase product.

The remaining -4.67° and -20.11° values are the observed diagnostic disagreements for these two saved visits, not validated uncertainty bounds. They do not establish a physical effect. A synthetic test with a deliberately ±30 Hz authority error recovers the true inter-frame relative frequency while retaining the expected ±1.52° phase shift between the actual pilot centroids. Thus a shared rotation cancels receiver-specific alias choices but cannot erase a real error in the supplied differential authority.

Wrong-symbol controls at broadband authority ±227272.73 Hz retain resultants of 0.897–0.979 and exact-to-control floors of 4.30–23.37 while reporting the wrong relative frequency. Pilot coherence therefore cannot validate the externally supplied symbol branch. The broadband authority remains required and must be accurate within the principal 750 Hz inter-frame interval.

The replay used only saved visits 1354 and 1428. No RF was collected. Numerical evidence is in `reports/figures/2026_09_21_phase_half_audit/scan-hop-6adcb067e2dbce43-shared-residual-two-visit-v1.json`. Reproduce it with `sudo -u leo env PYTHONPATH=src .venv/bin/python tools/report_adaptive_dual_rx_shared_residual_audit.py --bulk-root /srv/bulk/leo --session-id scan-hop-6adcb067e2dbce43 --json /tmp/shared-residual-audit.json`.
