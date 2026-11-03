# Verified causal orbit freshness: one material single-scan gain

Updating only orbit states from snapshots proven published before capture
reduces original scan31's reference error from **8052.49m to 4666.36m**.
All five metadata-selected fits qualify; the other four change by less than
one metre. The 27 scans with unchanged selected elements retain their exact
original outputs. This is an exploratory improvement, not replicated evidence
of lower typical single-scan error.

| Full original panel | Original IID | Verified causal freshness |
|---|---:|---:|
| Qualified outputs |32/32|32/32|
| Median error |2759.38m|2759.38m|
| Mean error |3784.91m|3679.08m|
| P90 error |7708.23m|7342.24m|
| Maximum error |8540.08m|8540.08m|
| Below 1km |2|2|

The five paired error changes, in index order 10,13,16,27,31, are
0.00m, -0.51m, +0.11m, -0.03m and -3386.13m. All four-start fits complete in
19.7–42.3 seconds, below the 90-second cap. No fallback or failed-output
exclusion is used. The existing reference remains an unsurveyed installation
coordinate; its limitations apply to these errors.

## What changed and why it is causal

The original exporter uses snapshots requested before capture start minus
505 seconds. The collector timestamps a request before downloading bytes.
For the five selected replacements, exact archive hashes, local file times and
matching journal publication receipts establish completion 42.9–469.4 seconds
before capture. This establishes availability for these particular records;
it does not justify globally treating request timestamps as completion times.
No post-capture data is used.

The [prospective protocol](PROTOCOL.md) freezes indices from metadata rather
than reference errors. Candidate physical identities/order, shortlists, track
membership, measurements, masks, catalogue normalization, t4/100Hz likelihood,
CFO profiles, bounds and optimizer starts are unchanged. Only position and
velocity states change; normal visibility evaluation uses those new states.
Each old element was first repropagated at every original observation and
timing node: all five banks reproduce their original states exactly, with
zero measured position or velocity discrepancy.

Most changed TLE bytes are input-equivalent or differ only in eccentricity
rounding. Scan31 contains twenty genuinely newer candidate epochs, including
two conditional training-MAP identities spanning eight tracks. The observed
gain therefore supports a narrowly scoped freshness correction, not arbitrary
orbit deformation or a claim that all errors are caused by orbit age.

## Predictive and numerical checks

For scan31, at the old position, the fresh bank improves training score by
439.28 nats and held score by 251.31 nats relative to the old bank. Refitting
position under the fresh bank adds 73.57 training nats and 16.62 held nats.
CFOs are fit only on training observations. The old-bank held score worsens at
the fresh position, which illustrates why a diagnostic scored under stale
orbits should not be mistaken for the fresh model's predictive performance.
The [conditional association audit](association.json) finds no MAP identity
changes among 64 tracks when only orbits change at the original position.
Three MAP identities change after the position is refit. Thus the full gain
includes the ordinary coupling between location and the candidate mixture;
these fitted identities are not independent identification truth.
Seven tracks conditionally assigned to NORAD61725 account for 439.04 of the
439.28 training nats gained by changing orbits at the fixed original position.
The old-orbit four-start control (`runs/control/original_31.json`) exactly
reproduces the original 8052.49m error; score differs by only1.46e-11 nats and
all position/time parameters by less than2e-14. Extra optimization starts do
not explain the observed gain.
Within-track held observations still share extraction and orbit errors with
training; this score is not separate geographic validation.

Five wrapper tests and three preparation tests cover unchanged-model parity,
state isolation, candidate slots, derivative agreement, held independence,
completion binding, changed-element identity and nonfinite/replay rejection.
An independent review checked the implementation and all five real patches,
including complete coverage of every changed satellite occurrence. Input,
source, array and receipt hashes are retained; original exports are untouched.

[assessment.json](assessment.json) contains all attempts and full-panel metrics.
[predictive.json](predictive.json) records both banks at both endpoints.
`patches/` contains bound replacement arrays; `runs/causal/` retains every
optimizer start and terminal receipt. A separate eligible-scan confirmation
is required before treating this as a general performance improvement.
The [additional12 eligibility inventory](../additional_causal_inventory/README.md)
finds no snapshot update in any pre-capture 505-second window across its 1124
scan-candidate occasions. There is therefore no changed-input confirmation arm
to fit on that panel; unchanged predictions must not be called replication.
The subsequent [five-scan confirmation](../causal_fresh_confirmation/README.md)
fails its frozen gain criterion: three exact no-ops and only sub-metre changes
on the other two. Its sole newer-epoch bank candidate has essentially zero
conditional fitted support, so the panel supplies no informative replication
of the strongly supported-source correction on original index31. A general
accuracy improvement remains unverified.
