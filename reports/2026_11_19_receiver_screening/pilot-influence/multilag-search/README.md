# Three-lag Qin pilot timing

The new scout recovered **2 of 9** previously missed physical pilots and **2 of 6** independently held misses. All four recovered pilots became their receiver's winner. The released four- and five-center detectors reproduced their stored outputs byte for byte and recovered zero of the selected misses. The new detector kept all four natural positive controls and returned zero gated candidates on both natural negative windows. [Detector chart](multilag-search.pdf) · [Qualification data](qualification.json)

## Same-IQ benchmark

The primary panel reinstates all 11 visits from the representative-half experiment, which recovered one of those nine misses. The ten held visits come from different segments and include one common miss from each of the six hard recordings, two natural positive controls and two gate-negative visits. Both antenna lanes in every visit went through each detector. Physical matches allow circular epoch distance of two samples and 1 kHz of signed, unfolded CFO. [Frozen selection](source-lock.json) · [Previous representative-half replay](../../receiver-choice/hard-pilots/README.md)

| Native detector | Primary misses recovered | Held misses recovered | Held and primary positives | Gates | CPU p50 | Wall p50 / p95 | Wall ≤20 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Four centers | 0/9 | 0/6 | 4/4 | 90 | 15.90 ms | 15.96 / 19.36 ms | 60/63 |
| Released fifth | 0/9 | 0/6 | 4/4 | 94 | 19.36 ms | 19.80 / 22.60 ms | 34/63 |
| Three-lag fifth | 2/9 | 2/6 | 4/4 | 108 | 25.79 ms | 26.86 / 31.43 ms | 0/63 |

The common coarse collector preserved all 4,090 original peak keys before the top eight. Three-lag timing changed 23 of 42 requested receiver hints. The candidate added 14 gated hypotheses relative to released fifth with zero losses under one-to-one alias-aware matching. On recovered pilots, the largest observed error relative to the original was 44.4 Hz and 0.0091 sample. [Receipts and ordered candidates](waveform.json.gz) · [Individual timings](timing.csv)

Zero and Gaussian inputs produced zero gates. The upper-edge tone produced the same eight gates in all methods. Released and three-lag fifth both recovered the four one-frame physical lane targets while stock recovered zero. All methods retained the eight signed strong and weak lane targets. The sampled positives establish physical candidate recovery within this roster. They do not establish a change in useful tracks or geographic error.

## Phase normalization and cost

The existing FFTW workspace correlates centered lag products at 44, 88 and 132 samples against exact and shifted Qin codes at all three frame residues. It normalizes each complex response by the square root of available coded reference energy times measured centered data-product energy. For a common carrier, increasing the lag multiplies its phase rotation by two or three. The scout downweights exact responses whose signed rotations disagree and subtracts the three control powers before ranking. These rotations repeat every 227.27 kHz, so signed physical CFO selection stays with the unchanged multi-CFO GLRT and its gates. The original timing regions are retained and one additional winner is allowed per receiver. [Frozen rule](PROTOCOL.md)

The new scout used 10.05 ms median host CPU, with a paired median increase of 6.76 ms over the released scout. Complete paired median increases were 6.78 ms CPU and 6.93 ms wall. The full boundary starts with an in-memory dual 20 ms IQ visit and ends with native candidate output. The measured calls were warm on CPU 4 with one numerical thread. The result does not meet a 20 ms detector deadline on this host. It does not measure receiver hardware, archive decoding or positions.

## Reproduce

Reuse the current center-union release with `tools.pipeline_eval.variants.multilag_search.MultilagScout(library, edge)`, a callable replacement for the existing FFTW timing scout. The build uses GCC and the FFTW float development and runtime libraries. The compiled scout shared object is 24,480 bytes. Use `python -m tools.pipeline_eval.qualification.multilag_search_eval build --work /path/to/local/build` for an isolated sidecar build. [Build and input hash](source-lock.json)

```sh
python -m tools.pipeline_eval.qualification.multilag_search_results --out /path/to/local/output
```

The chart and CSV use sealed receipts in the checkout. [Evidence seal](evidence-lock.json)
