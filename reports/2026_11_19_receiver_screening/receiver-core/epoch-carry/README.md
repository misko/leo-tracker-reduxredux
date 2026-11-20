# Pilot epoch carry across receiver retunes

Same-lane carry recovered zero missed capture-era pilot starts on eight full wide waveforms. The initial 120 ms bound admitted no forecasts because actual lane revisits took at least 352.6 ms. Each recording's median revisit fell between 354.3 and 354.6 ms. A separate 400 ms diagnostic fixed that coverage issue using hardware timing alone, then sealed its forecasts before scoring.

The one-cycle variant emitted 7,077 forecasts over 103,632 processed receiver probes. Of these, 23 had a corresponding positive capture-era target, and the current wide detector missed those target identities. All 23 same-lane epoch errors exceeded 1,000 samples, including comparisons without the CFO identity requirement. On the 15 common probes, both the same-lane and wrong-channel controls exceeded 1,000 samples in every case. The one-third-frame wrong-time control gave two errors from 20 to 100 samples, five from 100 to 1,000 and eight above 1,000. None of the three methods approached the ±1-sample scout radius.

The next wide probe had any accepted pilot on only 14 of the 7,077 forecast opportunities. None of those agreed with the predicted CFO within 1 kHz, allowing the usual frequency alias. Removing the phase and CFO link checks still gave just 37 next positives following 7,501 earlier same-lane runs of three wide-positive probes in 1.2 s. This tests recurrence in the stored detector factors. Other transmitters, shorter histories and acquisition schedules remain outside the measured rule.

## Independent pilot-energy score

A second prototype spent one possible fourth scout slot on the known pilot's CFO-invariant power envelope. The native harness verified the exact original first four centers. On 16 separately selected dual-RX saved-IQ windows, no independent power peak qualified to change any of the 32 scout lists. Both lists admitted 13 of 18 capture-era starts within ±1 sample and 16 of 18 within ±2. One of four planted receiver lists changed while all four planted starts stayed covered. Both noise-only IQ windows retained the original starts.

Median x86 allocation CPU for the Python envelope was 7.65 ms per recorded dual-RX window. The original C scout took 1.53 ms on the same windows. The original GLRT ran on the actual IQ for reference. The envelope result is a shadow comparison of the timing lists. These results support keeping the ordinary four-start proposer on the tested waveforms.

[Short holdover protocol](PROTOCOL.md) · [One-cycle scores](cycle/scores.json) · [Three-way histogram](cycle/timing-histogram.png) · [Independent envelope results](envelope/scores.json) · [Evidence seal](audit-lock.json)
