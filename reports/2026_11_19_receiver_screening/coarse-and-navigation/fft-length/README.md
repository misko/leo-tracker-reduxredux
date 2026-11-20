# Prepared GLRT with a stored 256-point FFT plan

The 256-point bank with stored FFTW measured plans reduced median paired complete detector CPU by **15.60 ms (4.18%)**, wall time by **15.62 ms (4.17%)**, and coarse CPU by **17.51 ms (9.13%)** across 40 matched real pairs. All **128 ordered public candidates** and **29 fractional gate positives** agreed with the installed and qualified prepared detectors. [Stage chart](stage.pdf) · [Plotted measurements](stage.csv) · [Qualification](qualification.json)

## Development-only selection

The detector still forms a separate complete spectrum for each anchor and CFO. Each overlap-save block uses one shared input FFT. With 44 taps, a 256-point block supplies 213 valid starts, and a 512-point block supplies 469. Both include the same partial frame support, sample energy and template normalization. The 512-point rebuild reproduced the released binary byte for byte.

| Length | FFTW estimate CPU / released 512 | Stored measured plan CPU / released 512 |
| ---: | ---: | ---: |
| 64 | 2.3695 | |
| 128 | 1.5571 | |
| 256 | 1.0075 | 0.9160 |
| 512 | 1.0000 | 0.9512 |
| 1,024 | 1.0546 | |
| 2,048 | 1.9115 | |

The paired ratios use five warm calls per length across both receivers and both anchor counts of the two development visits. All eight development grids retained the original ordered coarse keys at every estimate length. The two fastest estimate lengths advanced to the measured-plan comparison. The stored 256-point plan won on development timing and its binary was fixed before any held call. The FFTW wisdom was generated for the original 21-lane inverse batch. A worker imports that wisdom only while constructing the plan and restores its previous wisdom afterward. [Development selection](selection-lock.json) · [Measured-plan bindings](planning-lock.json) · [Protocol](PROTOCOL.md)

## Held outputs, timing, and memory

The eight held visits cover four recordings, both pilot edges and three installed producer roots. Every real and control payload preserved the retained basin keys, acquisition order, signed CFO, epochs, exact and control scores, margins and acceptance of every published candidate. The eight signed ±720 kHz physical control lanes all passed. Both empty controls returned zero candidates, and both near-equal planted contender controls reproduced the installed payload. The largest measured difference across 6,159,846 real coarse score cells was **1.51 × 10⁻⁸**; the smallest observed retained-step gap was **3.98 × 10⁻⁷**. Component tests also covered exactly tied CFO rows, mixed taps and clipped final frames. [Ordered payload decisions](decisions.csv) · [Retained rank and score audit](rank-audit.json) · [Paired timing records](timings.csv)

Named FFT buffers fell from 1,212,416 to 606,208 bytes per 12-anchor cache entry and from 2,072,576 to 1,036,288 bytes per 22-anchor entry. These counters cover the bank arrays and scratch. The paired process included both native implementations. The largest resident high-water observed on a real visit was 205,832 KiB, with 223,640 KiB across all visits and controls. The complete comparisons kept the same row-wise selector, AVX2 batched fine stage, and qualified conditioned and fractional stages. [Held source and build freeze](held-lock.json)

## Receiver handoff

The measured [256-point shared library](build/planned-256/prepared_measured.so) uses the released prepared-bank ABI. Use `original_kernel.PersistentGrid` with that path as the `prepared` library and retain the installed acquisition and screen routes. The library SHA-256 is `40965b750fb0e833fd211f4c069bb3eb0f190a40a0cf65963a2e5ebbe6456286`. The host build, generated C header and wisdom are preserved alongside the binary. The measured comparison ends at detector output. [Artifact seal](evidence-lock.json)
