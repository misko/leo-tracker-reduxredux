# Receiver deadline measurements

Roof plots compare each study on its scheduled recordings against all four original v5 options. Matched stock fits use the inputs and solver boundary described on each page. Blank rows retain failed or withheld attempts in the denominator. Diagnostic estimates appear only when a receiver saved one.

Wrong-region and independent-site results have their own figures. V5 enters only the paired original-tile comparisons. A false published point remains visible.

## Roof comparisons

**Fitted calibration** · [PDF](fitted_c/modifications.pdf) · [Per-sample CSV](fitted_c/modifications.csv)

- [Use the original pair on overlap · Two detectors running concurrently on the recording clock](fitted_c/parallel-concurrent-replace.png)
- [Fill a missed antenna from the original · Two detectors running concurrently on the recording clock](fitted_c/parallel-concurrent-fill.png)
- [Keep only packets within 20 ms · Two detectors running concurrently on the recording clock](fitted_c/parallel-concurrent-timely.png)
- [Use the original pair on overlap · Detector runs on separate clocks aligned to the recording](fitted_c/parallel-separate-replace.png)
- [Fill a missed antenna from the original · Detector runs on separate clocks aligned to the recording](fitted_c/parallel-separate-fill.png)
- [Keep only packets within 20 ms · Detector runs on separate clocks aligned to the recording](fitted_c/parallel-separate-timely.png)
- [Distilled pilot admission on the held narrow detector roster](fitted_c/pilot-distillation-narrow.png)
- [Distilled pilot admission on the held wide detector roster](fitted_c/pilot-distillation-wide.png)
- [Position from the exact lane peak selector](fitted_c/lane-peak-selector-waveform.png)
- [Cumulative compact release and full fallback](fitted_c/sequential-fix-roof.png)
- [Two-rate replay at the ordinary compact deadline](fitted_c/two-rate-holdout-first-attempt.png)
- [Two-rate accuracy with same-input timeout retries](fitted_c/two-rate-holdout.png)

**Zero calibration** · [PDF](c0/modifications.pdf) · [Per-sample CSV](c0/modifications.csv)

- [Use the original pair on overlap · Two detectors running concurrently on the recording clock](c0/parallel-concurrent-replace.png)
- [Fill a missed antenna from the original · Two detectors running concurrently on the recording clock](c0/parallel-concurrent-fill.png)
- [Keep only packets within 20 ms · Two detectors running concurrently on the recording clock](c0/parallel-concurrent-timely.png)
- [Use the original pair on overlap · Detector runs on separate clocks aligned to the recording](c0/parallel-separate-replace.png)
- [Fill a missed antenna from the original · Detector runs on separate clocks aligned to the recording](c0/parallel-separate-fill.png)
- [Keep only packets within 20 ms · Detector runs on separate clocks aligned to the recording](c0/parallel-separate-timely.png)
- [Distilled pilot admission on the held narrow detector roster](c0/pilot-distillation-narrow.png)
- [Distilled pilot admission on the held wide detector roster](c0/pilot-distillation-wide.png)
- [Position from the exact lane peak selector](c0/lane-peak-selector-waveform.png)
- [Cumulative compact release and full fallback](c0/sequential-fix-roof.png)
- [Two-rate replay at the ordinary compact deadline](c0/two-rate-holdout-first-attempt.png)
- [Two-rate accuracy with same-input timeout retries](c0/two-rate-holdout.png)

## Wrong regions and new sites

**Fitted calibration** · [PDF](fitted_c/transfer.pdf) · [Per-sample CSV](fitted_c/transfer.csv)

- [Position decisions at the independent Watson station](fitted_c/watson-spectrum-transfer.png)
- [Cumulative compact with the offered square moved east](fitted_c/sequential-fix-shifted.png)
- [Early and fallback positions in a verified omitted square](fitted_c/sequential-fix-omitted.png)

**Zero calibration** · [PDF](c0/transfer.pdf) · [Per-sample CSV](c0/transfer.csv)

- [Position decisions at the independent Watson station](c0/watson-spectrum-transfer.png)
- [Cumulative compact with the offered square moved east](c0/sequential-fix-shifted.png)
- [Early and fallback positions in a verified omitted square](c0/sequential-fix-omitted.png)
