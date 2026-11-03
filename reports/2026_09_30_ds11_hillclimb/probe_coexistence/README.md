# Four of six shared probes support additive pilot contributions

On identical held raw samples, the two-candidate pilot model outperforms each
single candidate and both code-rolled controls in four of six selected scan0
probes. This is evidence against imposing one active candidate per shared
probe. It is not proof of independent satellites, an authenticated identity,
or a geographic improvement.

| Pair / visit | Best single held NMSE | Joint held NMSE | Gain over best single | Beats both rolled controls too |
|---|---:|---:|---:|---|
|0 /736|0.946611|0.925256|+0.021355|Yes|
|1 /671|0.953455|0.954800|-0.001344|Yes, but loses to single|
|2 /788|0.919890|0.896152|+0.023738|Yes|
|3 /549|0.935363|0.905734|+0.029629|Yes|
|4 /646|0.987898|1.002421|-0.014524|No|
|5 /536|0.955791|0.938151|+0.017640|Yes|

Lower NMSE is better. Positive gain is an absolute normalized-error difference,
not a percentage gain in position accuracy. All six probes and all outcomes
are retained. The two negative cases are not replaced or declared exclusive.
The three fixed single-candidate controls favor their correct pilots over the
rolled sequences: NMSE0.9580 versus1.0027,0.9730 versus1.0118, and0.9724
versus1.0019. They support transfer of the simplified waveform convention to
these excerpts, not full calibration of the assay.

Selection precedes IQ reads: sort shared training-probe IDs in scan0, use the
first two distinct candidate IDs, and choose the first six with sufficient
common samples in their first frames. Nine groups are considered; three lack
common held coverage and remain in the manifest. Eligibility uses timing only.
Selected probes cover both10.71GHz and11.21GHz and both receivers, although
five of six use RX0. This is a small metadata-selected sample, not a population
estimate of coexistence prevalence.

All arms fit independent complex gains for known pilot carriers on exactly
the same raw samples lying inside both candidates' symbols22–221. They are
evaluated on identical held samples inside both candidates' symbols222–301.
Epochs and acquisition frequencies are fixed. Joint models add the two pilot
contributions; controls replace either contribution's code by an11-symbol
cyclic roll. No native score across different observation sets is compared.
All designs have full column rank; joint condition numbers range1.17–1.30.

The model explains only known-pilot content, not unknown payload or complete
interference. Noise and filtering can be dependent; these are not calibrated
likelihood-ratio tests or false-alarm probabilities. A single rolled control
per candidate does not establish a detection threshold. Frequency/timing error,
other signals, channel variation and model mismatch can also affect outcomes.
Pilot contributions do not by themselves establish their physical transmitters
or catalogue associations.

Three synthetic tests pass: one versus two signals, isolation of held samples,
and an independent240MS/s native-IFFT/cyclic-prefix/resampling check against the
5MS/s design. All six pair cases and three real controls complete successfully
in one3.21second worker, below its120second cap. Existing visits are read through
the public read-only store with published-manifest and chunk validation; six
20ms excerpts are saved. No new RF or QNAP mutation occurs.
Independent QR solves reproduce every held NMSE to2.23e-16, while rechecking
all bound sources, saved excerpt hashes, masks and design ranks.

Evidence: [protocol](PROTOCOL.md), [frozen plan](plan.json),
[complete outcome](outcome.json), [QR verification](verification.json).
Plan SHA256:
`073514c5a5ec5ed64b3539660ee4302870a8d7719265f56addee51f4cecfc08a`.
No position fit, orbit update or geographic error evaluation is performed.

The next measurement experiment should compare joint and separate frequency
estimation on common raw samples, retaining both detections and all six probes.
It must use fitting samples for frequency selection and held samples only for
evaluation, preserve the negative cases, and establish numerical and synthetic
recovery before propagating frequency changes into positioning. The current
result does not justify hard exclusivity or multiplying all detection scores
as independent evidence.
