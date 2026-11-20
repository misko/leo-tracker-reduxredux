# Shared pilot spectra and low-rank coarse scoring

Keep the prepared 512-point bank for the original GLRT detector. Sharing CFO spectra preserved the complete published detector result on six held radio visits and ten synthetic controls. The best shared-spectrum variant increased median full detector CPU from **417.0 to 475.0 ms** on radio IQ. The float SVD variants preserved the retained coarse keys in development and took at least four times the prepared grid time. [Stage chart](stage.pdf) · [Plotted measurements](stage.csv) · [Detector decisions](decisions.json) · [Protocol](PROTOCOL.md)

## Structure of the installed bank

The three capture releases use identical pilot-template source and produce identical normalized banks. For a single CFO, the 12- and 22-anchor banks have nine singular directions above the complex64 rounding floor. Eight correspond to the Qin tones and the ninth to the symbol-boundary tap. All 12 or 22 relative QPSK rotation patterns are distinct. Among the complete filtered bank, the strongest distinct phase-equivalent pair had normalized overlap 0.9472. Allowing conjugate time reversal gave at most 0.8554. The complete bank has 44 nonzero singular directions. Its maximum residual norm across the four edge and anchor combinations is 0.1923 at rank 16, 0.001962 at rank 20 and 0.000004314 at rank 24. These are coefficient errors for unit-norm filters. [Shared bank](shared-bank.json) · [Standard bank](standard-bank.json) · [Screened bank](screened-bank.json)

The shared-spectrum variant factors a CFO shift into circular indexing of one overlap-save filter spectrum per anchor. The scalar phase from reversing the 44 taps cancels in the magnitude. An 80 kHz step at 10 Msps is four bins per lane for a 500-point transform. Each cache entry stores two adjacent copies of each central spectrum to preserve contiguous accesses. A cold primary key needs 12 reference transforms instead of 252. The named FFT buffers fell from 1,212,416 to 272,000 bytes with 12 anchors, and from 2,072,576 to 352,000 with 22 anchors. All carrier inverse transforms remain. The 500-point length increases the measured number of inverse calls from 104,286 to 106,974 on the primary geometry. [Per-grid transform and timing records](coarse-timing.csv)

## Development grid timing and recall

Values are median host CPU milliseconds per receiver grid across three recordings, two lanes per recording, and five rotating warm comparisons. Both anchor counts are explicitly evaluated on each of the six IQ lanes. The 22-anchor bank also ran as the detector's actual fallback on two held visits.

| Bank | 12 anchors | 22 anchors | Maximum dense score difference from installed |
| --- | ---: | ---: | ---: |
| Prepared 512 | 53.55 | 97.76 | 2.27 × 10⁻⁸ |
| Shared 250 | 107.03 | 192.76 | 1.85 × 10⁻⁸ |
| Shared 500 | 75.69 | 134.49 | 1.77 × 10⁻⁸ |
| Shared 1,000 | 82.73 | 148.71 | 1.69 × 10⁻⁸ |
| SVD rank 20 | 272.52 | 429.93 | 4.39 × 10⁻⁵ |
| SVD rank 24 | 293.27 | 460.65 | 9.24 × 10⁻⁸ |

Both SVD ranks preserved all 96 ordered retained keys before repair. Offline exact repair retained all 96 keys again using 4,992 installed score cells for rank 20 and 4,990 for rank 24. The nomination cap was 32 and repair covered the nominated lane's circular ±6-sample neighborhood. There were zero observed missed or excess keys. A true maximum can still fall outside those neighborhoods on other inputs. Each rank-20 grid needs only 8,540 inverse transforms, but reconstructs approximately 1.01 billion complex multiply-adds for 12 anchors and 1.85 billion for 22. The nonlinear magnitude requires reconstruction before the original frame-and-anchor fold. The measured float implementation spends more time on reconstruction and folding alone than the prepared bank spends on its entire grid. [Lower-edge development](DS26-0237-development.json.gz) · [Upper-edge development](DS29-0082-development.json.gz) · [Screened lower-edge development](DS29-0519-development.json.gz)

## Held original detector

The prepared and shared 500 variants ran the same later stages in the original detector. All 96 public candidate records agreed, including fractional epoch, signed CFO, exact and control score, raw margin, rank, gate and receiver. All 21 gate-positive fractional candidates matched the archived installed result. All five alternating runs per visit reproduced the same payloads and acquisition paths. Median wall increased from 427.4 to 497.7 ms. All planted signed and weak controls produced a physical match on both receivers and edges. Empty and seeded Gaussian controls passed zero gates in both arms. [Per-visit timings](detector-timing.csv) · [DS26-0237 output](DS26-0237-held.json.gz) · [DS29-0082 output](DS29-0082-held.json.gz) · [DS29-0519 output](DS29-0519-held.json.gz)

## AVX-VNNI reconstruction with native revisits

The follow-on quantized the rank-20 mixing coefficients per filter and the basis responses per 512-position tile, and used unsigned-by-signed byte dot products on the same Intel host. It ran both geometries and both receivers of the lower and upper development captures in five alternating pairs. The same 32 nominations supplied circular ±6-sample neighborhoods on the proposed CFO. The native sparse scorer computed exact FP64 columns for those neighborhoods, grouping the requested lanes in two hardware tiles. The real revisit preserved all **64/64** original retained coarse keys after repair. The maximum dense proposal error was 0.000539, no response tile clipped, and revisited scores were within 8.33 × 10⁻¹⁷ of the installed full grids.

The reconstruction and fold took around 36 ms with 12 anchors and 60 ms with 22. The authenticated sparse revisit added around 47 and 52 ms respectively. Those two stages alone cost more than the prepared complete grid, before computing the basis FFTs. The paired complete int8 proposal and revisit took **220–392 ms** across the eight receiver geometries. This benchmark measured a host AVX-VNNI implementation and stopped at coarse selection. [Lower edge](DS26-0237-int8.json.gz) · [Upper edge](DS29-0082-int8.json.gz)

## Reproduction

Run `tools.pipeline_eval.qualification.coarse_basis_eval` with `build <scratch>` and `freeze <scratch>` using the capture Python and a local scratch directory. For each case, put the installed source root in its receipt first on `PYTHONPATH`, set the numerical thread variables to one and pin CPU 2 or 3. Run `development <scratch> <case>` and `held <scratch> <case> --fft-size 500`. The optional integer probe uses `tools.pipeline_eval.qualification.coarse_basis_integer_eval <scratch> <case>`. `tools.pipeline_eval.qualification.coarse_basis_results <scratch> <output>` rebuilds the chart and receipts. The trial ends at the detector stage. [Source and compiled inputs](source-lock.json) · [Evidence hashes](evidence-lock.json)
