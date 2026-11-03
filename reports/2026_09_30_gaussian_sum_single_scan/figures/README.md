# First-scan diagnostic figures

These figures use only checksum-verified sealed receipts. The Gaussian-sum
regional run failed the frozen promotion gate after factor 17 discarded 13.01%
of posterior mass. Its maps and timelines are diagnostics, not accepted
posteriors. The greedy arm is a matched baseline and its final roof error is
0.518 km, compared with 0.809 km for the configured prior center/mixture mean;
this single unsurveyed-site result is descriptive rather than a calibrated
accuracy claim.

`DS9-F001-regional-gaussian_sum-first-density.png` compares the full local location
mixture after the first completed track with the regional prior.
`DS9-F001-regional-gaussian_sum-association-mass.png` shows association/background
probabilities and retained/discarded mass through the failed Gaussian-sum run.
`DS9-F001-regional-matched-location-density.png` compares the prior, both arms
at matched factor 17, and the complete 50-factor greedy endpoint. It uses one
common logarithmic density scale so both the diffuse prior and compact
posteriors remain visible without changing their relative density units.

The near-zero background probabilities require special caution. The first real
track changes by 40,357 Hz in 11.53 seconds, while the frozen background slope
prior has a 100 Hz/s standard deviation. Sharp association probabilities under
that restrictive null do not establish satellite identity truth.
