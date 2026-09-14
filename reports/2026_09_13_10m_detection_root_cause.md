# Detection collapse: receiver-dependent input, not a general 10 MS/s failure

## Finding

The recent sparse production captures selected physical RX1 on radio
`104000bac4950008230026001b440a003a`. Saved same-radio 10 MS/s qualification
captures show strong signals and detections on RX0, but nearly noise-only input
on RX1. The failure is localized to the RX1 acquisition/input path, upstream of
offline analysis and host decimation. The user subsequently confirmed that only
RX0 is connected to an antenna feed; RX1 is intentionally unconnected. No new RF
acquisition, radio settings change or scanner restart was performed for this
investigation.

| Same-radio 10 MS/s evidence | Adaptive RX0 canary | Adaptive RX1 canary |
| --- | ---: | ---: |
| Session | `scan-hop-89ff5771b72d879c` | `scan-hop-106c90486d2e961d` |
| Online detected visits | 1,448 | 0 |
| Online not-detected / unknown | 631 / 302 | 1,467 / 915 |
| Native overview selected observations | 1,063 | 1 |
| Native overview associations | 92 | 0 |
| First eight 20 ms probes, complex RMS in stored ADC counts | 65.79–209.08 | 2.44–2.52 |

Both canaries use native 10 MS/s, 10 MHz bandwidth, manual 40 dB gain and the
same eight tuned targets, release and detector. They were recorded sequentially,
not simultaneously; this is a strong receiver-path comparison, not a calibrated
RF transfer measurement. RX1 is about 28–39 dB lower in recorded RMS amplitude
than RX0 across these eight corresponding targets. These are ADC-count ratios,
not calibrated antenna power or SNR.

Production RX1 `scan-hop-8579105ea44ad910` repeats the same low amplitudes
(2.44–2.52 counts RMS in 24 probes spread across the recording), zero online
detections and one selected offline observation. Its 95.2555% capture duty and
complete healthy feedback show that successful transport does not imply useful
signal reception.

## Paired saved-IQ experiments

Replayed the first 20 ms of visits 0–7, 800–807 and 1600–1607 from the production
RX1 recording. All 24 native probes remained below the 0.025 fractional margin
gate. Independently low-pass filtering and decimating those exact samples to
2.5 MS/s did not recover detections; conjugating the decimated IQ did not recover
them either. This comparison does not merely reuse the production C decimator.

Replayed the first eight probes of both same-radio canaries. RX0 has strong
native margins of approximately 0.55–0.73 on four probes, with approximately
0.50–0.68 after independent decimation. RX1 remains below threshold in both
representations. Thus native 10 MS/s and decimated 2.5 MS/s both work when strong
signal is present on this radio.

As a separate positive control, replayed eight RX1 probes from the older
2.5 MS/s reference `scan-hop-befc3b3c70591364` and independently interpolated
them to 10 MS/s. Its three initially strong probes remain strong: margins
0.670→0.708, 0.348→0.403 and 0.531→0.576. Some initially weak probes also become
detectable after interpolation, so this is evidence against catastrophic rate
handling failure, not an assertion of exact detector equivalence at all rates.
The old reference used radio `5d4d`, not `003a`, and a different recording time.

Independent rate conversion used a centered 161-tap Kaiser-windowed sinc FIR
(beta 8.6), factor four, float arithmetic. It is an offline diagnostic with
different boundary/phase handling from the production Q15 causal filter.
The detector retains eight candidates and analyzes one 20 ms probe per replay;
this bounded experiment does not replace full-recording sensitivity testing.

Evidence script: `/var/tmp/leo-detection-rca.py`. Results:
`/var/tmp/leo-detection-rca.json`,
`/var/tmp/leo-detection-rca-scan-hop-89ff5771b72d879c.json`, and
`/var/tmp/leo-detection-rca-scan-hop-106c90486d2e961d.json`.
The source reader was the public read-only adaptive IQ store. Numerical work
used the deployed interpreter and detector with BLAS/OMP/MKL limited to one.

## Setup and contributing factors

PPU `configure_source_locked_receiver_geometry` selects the requested physical
channels, applies manual gain to each selected channel, and checks rate,
bandwidth, channel identity, gain mode and gain readback. Inspection found no
obvious RX0-only gain assignment when selecting RX1. This source check is
consistent with the confirmed external wiring.

Random selection permits consecutive RX1 recordings; it does not alternate RXs.
That exposes the weak path and explains why recent production looks far worse
than the RX0 canary even though both are 10 MS/s. Adaptive feedback correctly
keeps targets inactive when no detections occur; uniform coverage is a consequence,
not the cause of the signal loss.

Deployment qualification verified continuity, duty, healthy feedback, policy
execution and web artifacts. It did not require independently demonstrated signal
reception on each eligible RX. Consequently RX1 passed transport qualification
despite its empty scientific result. The previous deployment conclusion was too
broad if read as evidence of comparable detection sensitivity on both inputs.

## Corrective direction

Only RX0 has a valid feed, so production should be restricted to RX0 while the
wiring remains unchanged. The existing random-RX profile was not changed by this
RCA or by publishing its web explanation. Do not lower detector thresholds to
conceal absent input signal.

The production UI links a concise version of this RCA from native radio003a
Adaptive Scan details at `/reports/radio003a-rx-input-rca.html`.

Separately, cross-channel trajectory/TLE plots remain unavailable because these
captures lack qualified UTC timing. That does not cause the missing GLRT/CFO
detections, which use device-relative timing.
