# Inventory for the scan-0 NORAD-65512 waveform pilot

This directory prepares a measurement-only known-pilot frequency audit for the
two original-IID scan-0 tracks conditionally assigned to physical NORAD 65512.
The assignment is not an authenticated satellite identity.

The frozen source diagnosis identifies two receiver-0 tracks:

| Track | RF / channel | Observations | Training | Localization-held |
|---|---:|---:|---:|---:|
| `sha256:e29fedf1…c88691` | 11.21 GHz / 3 | 71 | 46 | 25 |
| `sha256:42e1cbd0…a4536a` | 10.71 GHz / 1 | 105 | 65 | 40 |

The 111 training observations use 111 distinct visits, numbered 1227 through
1602, from `scan-fw-a32c07775a887379`.  The recording is a minted DS11 member at
5 MS/s with 2,218 complete visits and no admission exclusion.  Its frozen raw
manifest digest is `sha256:65fb09f5…48a890`; its chunk inventory digest is
`sha256:ef03634f…02c9a15`.  DS11 references the IQ in the read-only source store;
it did not copy or freshly rehash the payload and has no enforced retention
hold.  Actual chunk readability is therefore an outcome of this pilot.

Reading one 120 ms dual-receiver 5-MS/s visit for every selected observation is
bounded at 532,800,000 decoded bytes (508.12 MiB).  Saving one 20 ms, one-receiver
excerpt per observation requires 44,400,000 data bytes (42.34 MiB), before small
NumPy headers.  Existing extraction evidence recovered 106 DS7–DS9 excerpts in
two 120-second invocations (58 then 48).  The prospective limit here is three
checkpointed 120-second invocations and one 180-second measurement process.

No existing waveform artifact contains either exact track ID.  Earlier direct
known-pilot frequency studies used DS7–DS9: 18 single excerpts, 54 A/B/H
excerpts, and 106 four-point excerpts.  The sparse geographic shadow applied 72
direct DS7–DS9 training corrections.  The all-track symbol census selected one
pilot-ranked excerpt per DS7–DS9 track and was later extended through DS10, but
it did not estimate DS11 Doppler corrections.  This is the first planned DS11
known-pilot frequency audit for these tracks.

Preparation reads tracking metadata through public ports but does not open IQ.
No extraction, waveform fitting, localization fit, geographic scoring, held
localization change, RF collection, or QNAP mutation has occurred at preparation
time.

