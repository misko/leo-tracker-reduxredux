# Frequency branch complete: RF_NOT_QUALIFIED

No production changes, new RF, extra campaign, position calls, commits or push.
All work stays in frequency/. The primary owner integrates and publishes.

- Frozen v1 protocol: a969714196d0275457922f029c58741640b17c43a1268afea115dcd47e5f999d.
- Eleven tests pass; verification.json checks source/input freezes, runtime,
  exact round3 later-score parity, all denominators and bounded jobs.
- Strong synthetic accuracy136/144proposal versus96/144later-bin; weak75/144
  versus78/144.288comparisons reuse48independent later Gaussian vectors.
- Predeclared evolution subset: -12dB, donor-error0, ZERO forecast rate,
  true-rate +/-2000Hz/s,16distinct later vectors.14/16accurate; through-origin
  slope sum((rate*.354)*(proposal-carry))/sum((rate*.354)^2)=1.0085628531.
  Validator uses the SAME subset but midpoint truth(.359s,+/-718Hz), yielding
  slope0.994516; this report uses target-start change(.354s,+/-708Hz).
- Recorded accurate recovery3/16proposal,4/16unchanged,11/16carry. Correct-donor
  RMSE improves350.12->179.22Hz but fails the frozen100Hz recovery criterion.
  "Unchanged later bin" is donor-conditioned, not blind later acquisition.
- Zero/64conditional null false confirmations in each one/three-proposal stratum;
  exact one-sided95%upper bound4.573% each. No eight-proposal/deployment FAR claim.
- Review found v1 cumulative-grid-center quantile bias. Frozen estimator/outcomes
  preserved. Separately sealed OFFLINE interval_audit_v2 changes no likelihood,
  prior, weights, CFO, gate or RF calls. Synthetic coverage267/288v1,
  267/288discrete,262/288bin-density; recorded11/15,10/15,10/15. RF weights remain
  unqualified. Concentrated/symmetric/offgrid/boundary tests pass.
- Natural192half-packets retain96cells:5eligible/8modes,91no eligible donor.
  All8modes fail later both-half support. Mapping uses earlier forecasts,
  public native source/generation/IQ-digest metadata and exact support; zero new
  natural IQ reads or frequency calls. No relaxed matching or mode reselection.
  Both half-packets retain target-start CFO; second-half rate advance is omitted
  (approximately +/-26–39Hz). Those packets were never consumed by scoring.

FINDINGS.md, summary.json, four PNG/PDF figures, compact per-trial summaries,
reproducible tests, execution failures, publication allowlist and hash seals
complete the deliverable. Full synthetic/null grids remain local and immutable;
publication is lean. Raw later profiles are separate from conditioned posteriors,
and donor information never becomes a fresh independent Doppler point.
