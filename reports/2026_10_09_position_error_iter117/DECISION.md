# Endpoint diagnostic: strong nuisance confounding remains

All 12 frozen members completed in both arms, with no resource or input failures. All reconstructed endpoint objective differences are zero. No optimizer ran. Iteration117 corrects only iteration111's protocol-key admission error; iteration111 remains unchanged and unexecuted.

|Diagnostic median across 12 members|Fitted c|c = 0|
|---|---:|---:|
|Weaker raw frequency-Jacobian singular value, 1/km|107.979|107.412|
|Weaker nuisance-projected singular value, 1/km|2.892|3.016|
|Fixed-nuisance label missing-information trace fraction|2.258%|8.143%|
|Data-only projected spatial rank 2|12/12|12/12|
|Negative fixed-nuisance local observed eigenvalues|0/12|0/12|

Allowing the ordinary timing, receiver-clock and satellite-frequency nuisance span to move absorbs most conditional spatial frequency information, while both spatial directions remain numerically identifiable under the frozen rank rule. This is evidence of confounding at these endpoints, not a calibrated position uncertainty or proof of its contribution to position error. The label-ambiguity subtraction is smaller in the fitted arm, but the two arms have their own endpoint responsibilities.

The nuisance-relaxed complete-label PSD proxy and fixed-nuisance local observed spatial block have different conditioning; their sizes must not be interpreted as competing covariance estimates. Priors are stored separately, active bounds are omitted, and nonlinear frequency second derivatives are omitted. Visibility and alias windings are locally frozen. No matrix inversion, accuracy evaluation, new fit or full148 generalization is reported.

The immediate model action remains a coherent visibility-likelihood prototype to remove the independently demonstrated normalization discontinuity. This diagnostic does not justify tightening receiver or satellite priors: free nuisance projection can reveal a tradeoff without showing that those parameters are physically wrong. A future prior change needs independent physical evidence and matched-arm position validation. It also does not establish that label ambiguity or visibility caused the typical approximately 1 km position error.

Receipt elapsed costs sum to 151.403 seconds; concurrent wall time and peak RSS were not measured. The streamed QR preserved all rows and avoided the original dense-SVD workspace problem without dropping members. These 12 recordings are consumed development diagnostics. Production B7 is unchanged.

See [results and full coverage](RESULTS.md), [matrices and distributions](summary.json), and [plot](observability.png). The report was generated from the existing iteration111 reporter with its `HERE` global explicitly set to iteration117; its SHA is bound by the reporting integrity manifest.
