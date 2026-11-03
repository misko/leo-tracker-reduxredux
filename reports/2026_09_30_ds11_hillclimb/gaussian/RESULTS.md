# Gaussian endpoint screen

The frozen `wave1` screen completed all 24 attempts for `gaussian200`,
`gaussian400`, and `source_gaussian200` on indices 0, 4, 8, 12, 16, 20, 24,
and 28. Every process exited zero. Each arm qualified seven of eight fits and
failed the protocol screen.

| Variant | Qualified | Paired wins | Qualified median (m) | P90 (m) | Max (m) | Sub-km | Common IID held gain | Screen gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Gaussian 200 Hz | 7/8 | 3 | 2,720.52 | 10,586.84 | 12,292.34 | 0 | -715.14 | fail |
| Gaussian 400 Hz | 7/8 | 4 | 2,828.65 | 10,588.42 | 12,287.55 | 0 | -714.48 | fail |
| Source-balanced Gaussian 200 Hz | 7/8 | 3 | 2,817.80 | 9,930.75 | 11,559.48 | 0 | -902.97 | fail |
| Matched original IID | 8/8 | — | 3,108.16 | 6,046.04 | — | — | — | — |

All three arms failed index 12 scientifically at the allowed geographic
boundary. Both unweighted arms selected east/north `(-12, 12)` km from all
four starts. The source-balanced arm selected `(-12, 12, -5)` and therefore
also hit the timing boundary. Optimizers reported success and the derivative
audits passed; these are boundary outcomes, not numerical failures. The
qualified-only medians are lower than the matched IID median, but the protocol
requires all eight fits and the Gaussian tails are substantially worse, so no
Gaussian endpoint advances.

The Gaussian source SHA-256 is
`7724a2284e444bb2b9b2787f4daca4dc792be4bbb3b0a19dbb290f0fed4909ca`,
and all 24 results bind it. The source-balanced composite metadata additionally
binds source model SHA-256
`23d806106b7d144d93ee34440e4dbf3d276bfcf71a0a64e882168175b42f7cca`
and identity-sidecar SHA-256
`38ecdf6d7659eb575d3270b8404a1a8dd2fe20e6af9bdb7fc6e81211d11815cf`.
The largest finite-difference audit discrepancy was `5.54e-5`; the largest
selected qualified-fit gradient was `1.31e-4`.

Two Gaussian component tests verify normalization, analytic offset
stationarity, the profiled mixture gradient, and held-observation isolation.
All five imported source-balance component tests also pass, covering IID
parity, repeated-group weights, the weighted gradient, freeze isolation, and
the frozen public variant set.
