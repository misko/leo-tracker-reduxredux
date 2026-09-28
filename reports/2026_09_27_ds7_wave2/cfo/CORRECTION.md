# Superseding CFO method correction

> **Further superseded:** `LANE-CORRECTION.md` excludes visit 12 train-line
> transfer and reports only the channel/RF/track-eligible visit 11 diagnostics.

This correction supersedes the method interpretation in `README.md` and the
labels inside the immutable `results-v1.json`, `results-v2.json`, and
`results-final.json` receipts. Those runs computed the mean and median of the
same production phase-slope frame estimates. Their `ordinary_profile` label
means `phase_mean`, their `robust_profile` label means `phase_median`, and their
`differential_phase` value is the production aggregate, which is the same
median for these windows. They are not three independent waveform extractors.
Their held RMS values compare each method with its own held estimates, so they
only describe temporal self-consistency. They are not frequency errors and do
not measure accuracy.

`profile-spec-v3.json` froze a corrected comparison before its IQ read. It uses
the installed `ordinary_profile_cfo`, `robust_profile_cfo`, and
`differential_phase_cfo` functions on identical acquisition-bound, even-Qin
pilot matrices. Visits 5 and 8 alone fit each receiver/method UTC-linear
prediction. The prediction is scored on visits 11 and 12 with a common held
waveform objective: ordinary profiled coherence at that prediction. Held
frequency estimates and held profile optima never influence the prediction.

The final corrected run read 38,400,000 bytes through the public read-only IQ
port and took 4.59 seconds. Including every earlier Wave2 execution, cumulative
IQ was 153,600,000 bytes and measured analyzer time was 20.40 seconds. These are
below the original 512 MiB and 120 second leases. All 32 extraction rows were
supported. Mean held profiled coherence was:

| receiver | baseline | ordinary profile | robust profile | differential phase |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.07951 | 0.09621 | 0.09718 | 0.01933 |
| 1 | 0.07194 | 0.08068 | 0.07933 | 0.01686 |

Larger coherence indicates better agreement with the same held known-pilot
waveform objective. On these four windows, ordinary and robust profile
predictions have greater held coherence than the cached baseline prediction;
differential phase has less. This is a small, candidate-conditioned temporal
self-consistency result. It does not establish frequency accuracy, estimator
precision, calibrated false-support performance, population performance, or a
geographic improvement.

A deterministic wrong-pilot or phase-scramble negative control was requested
after the corrected process had released its matrices. It was not frozen
before that computation, and no additional IQ read was made merely to add it.
The false-support gate therefore remains unmet. No extractor is promoted and
no downstream geographic fit is supported by this result.

## Frozen identities

- Corrected spec SHA-256: `00c29341dbbf267f2ed056b526b8fe787ac1eed0b7def4afc2be38d553decc2e`
- Executed runner SHA-256: `ba1b1281f205d22fd7c292797a7af02b3bbf4abb7df74616ebc733c340cb77c9`
- Executed runner archive: `executed-profile-run.py`
- Corrected result SHA-256: `f406cf316e417d1a2266c686d48623f8952f9c32a60bb160df2b83f643a6303c`
- Installed `frame_cfo.py` SHA-256: `58d2cb8b1832afd4d44af24548ba75a3956fb5222ed0b28a055013b79fafbee5`
- Installed `pilot.py` SHA-256: `cbcf337be60ae971eb7064293d1dadd79cf6f5c004aa6f1aad142db068c39600`
- Reference audit: `reference_excluded`
