# Antenna receiver confirmation benchmark

`python -m tools.pipeline_eval benchmark --receiver antenna-confirmation --out OUTPUT_DIRECTORY` rebuilds the tables and seven position charts from sealed evidence. Open `OUTPUT_DIRECTORY/charts/index.html` to switch calibration settings and browse the PNGs, PDF books and `modifications.csv` point data. The 8 discovery and 14 later validation recordings form a 22-recording descriptive pool at one roof. The direct-IQ validation pair overlaps the held 14. The fresh direct pair has two different recordings and measures stock and partner-on-hit. The three other policies in the four-cell comparison are alternating primary alone, partner-on-miss, and both stock antennas. [Browse the seven charts](charts/index.html) · [Frozen analysis](PROTOCOL.md) · [Input and result lock](benchmark-lock.json) · [Position-chart inventory](chart-index.json)

## Independent validation

Adding the hit partner to primary alone reduced error on **11/14** with zero RF calibration and **10/14** with fitted calibration. Median paired changes were **−263 m** and **−222 m**, respectively. Adding the miss partner after enabling the hit partner increased error on **10/14** and **8/14**, with medians of **+32 m** and **+44 m**. The four registered tests had Holm-adjusted two-sided exact sign probabilities from **0.229 to 0.791**. All exceeded the registered 0.05 threshold. [Independent statistical verdict](verdict.json) · [Paired changes and RF contrasts](changes.csv) · [All contrast summaries](contrasts.csv)

| Holdout result | `c = 0` median / P95 | Fitted `c` median / P95 |
|---|---:|---:|
| Partner-on-hit | 0.742 / 2.424 km | 0.688 / 2.405 km |
| Stereo stock | 0.774 / 1.517 km | 0.765 / 1.375 km |

All four receiver cells published on all fourteen. Partner-on-hit met the +5% and +10% original no-repair v5 error allowances on **9/14** and **11/14** in the zero arm and **10/14** at both allowances in the fitted arm. Stereo stock reached **11/14** and **12/14** in the zero arm and **11/14** at both in the fitted arm. The held conditional RF median was **89.756/89.751 Hz** for partner-on-hit and **92.906/92.868 Hz** for stereo stock, zero and fitted respectively. [Cohort and calibration summary](summary.csv) · [Case-level tolerance pairs](tolerances.csv) · [Paired 5% and 10% counts](tolerance-summary.csv) · [Original v5 rows](reference-scores.csv)

## Measured saved-IQ replay

DS26-0168 and DS29-0174 reproduced their stored-projection native bytes, both calibration coordinates, and conditional RF exactly from saved IQ. They made **9,260** and **8,802** physical receiver calls. The corresponding complete decoded visit counts were **6,774** and **6,704**. The full services took **198.92 s** and **195.29 s**. These cases retain the overlap label in the benchmark; their positions already contribute to the fourteen-recording validation. [Versioned raw and position parity](raw-position-parity.csv) · [Calls and measured clocks](clocks.csv)

| Fresh recording | Whole wall, stock / hit | Error at `c = 0`, stock / hit | Error with fitted `c`, stock / hit |
|---|---:|---:|---:|
| DS26-0066 | 189.49 / 105.15 s | 2.201 / 2.379 km | 2.191 / 2.371 km |
| DS29-0085 | 156.73 / 83.87 s | 1.216 / 1.753 km | 1.093 / 1.628 km |

Both fresh policies published in both calibrations. Each met the original v5 +5% and +10% allowances on 1/2 fresh recordings in both arms. The conditional method ran faster and had larger geographic errors on both. Its fresh native inputs matched the stock-based projection byte for byte. Those two projection checks have no separately measured post-acquisition endpoints. The benchmark retains that distinction. [Geographic rows](scores.csv) · [Measured accuracy and wall time](accuracy-and-time.csv) · [Budget summary](budget-summary.csv)
