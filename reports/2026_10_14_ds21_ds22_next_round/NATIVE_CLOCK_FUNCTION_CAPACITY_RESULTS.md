# DS22-001: capacity to represent the separately fitted calibration functions

The current full native-clock calibration design cannot exactly represent the two selected half-band calibration functions stitched together at the native branch timestamps. Its best unregularized, unconstrained projection leaves 59.63 Hz weighted RMS error. Added receiver-by-band clock terms reduce that gap; adding band drift and RF contrast terms closes it numerically.

| Calibration design | Columns / rank | Low RMS (Hz) | High RMS (Hz) | Combined RMS (Hz) | Maximum absolute error (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing full design | 25 / 25 | 52.687502 | 67.466872 | 59.630610 | 281.359190 |
| Plus receiver × band clock interactions | 43 / 43 | 37.843746 | 51.274438 | 44.246699 | 170.488915 |
| Plus receiver band drift and one band RF contrast | 46 / 46 | 6.58e-10 | 5.57e-10 | 6.15e-10 | 1.80e-9 |

Inputs are the original-prior, training-selected low/high endpoints from the matched native-clock pilot. Geography, satellite timing, associations and residuals were not optimized. Only the saved receiver correction functions were evaluated: original baseline, receiver offsets and slopes, common RF coefficient, common receiver clock, and group offsets. The target uses the low endpoint on CH1–4 rows and high endpoint on CH5–8 rows. Native branch timestamps, receiver lifts, full-band frame and original baseline remain fixed.

Each original observation window receives total weight one, distributed equally over its available native branches. Projection uses column-scaled SVD with relative rank cutoff 1e-12, no ridge and no priors. Added clock columns multiply the original receiver clock basis by the receiver-specific centered band contrast. Added drift columns are the existing receiver band contrasts times native time relative to the unchanged training center. The RF column is the original centered RF design multiplied by a globally centered band contrast. Zero-coefficient baseline closure is exact. The final extended span reproduces the stitched functions within 1.81e-9 Hz. Minimum scaled singular values are 0.3405, 0.3322 and 0.3254, respectively; these matrices are full rank under the declared cutoff.

This establishes a representation gap for the current DS22 common-clock half functions, not a physical hardware diagnosis or improved position accuracy. Half-only fits can absorb geographic or satellite-timing errors into their calibration. Projection coefficients were unconstrained and unregularized: capacity does not imply the scientific optimizer can or should adopt them under its bounds and priors. The last step adds drift and RF terms together and does not isolate their individual contributions. Any next model experiment needs matched own-half controls and unchanged acceptance criteria.

This is distinct from the earlier negative DS21-039 band-capacity experiment without the current common-clock model. No temporal association activation or previously rejected DS21 model was repeated. No reference or held data were read.

Source `15ef48d97`; two component/driver tests and Ruff passed before freeze. Actual diagnostic completed in 47.57 seconds with zero objective evaluations and zero optimizer fits, under a 120-second cap. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-function-capacity-v1/report.json`, SHA-256 `bcc605cc88579bfb20b5f52b5a7086713a0df0f7ef9709c164c0fb0147f8d180`.
