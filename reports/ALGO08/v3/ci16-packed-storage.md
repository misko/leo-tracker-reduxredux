# Lossless CI16 packing through first mixed use

On the complete resident DS30-0016 first member, native measured-width CI16 packing saved **103.37 ms wall and 103.41 ms CPU** from capture through first mixed analysis. All three paired orders saved **84.94–106.38 ms wall**. Packing stored **76,799,710 bytes**, 1,931,566 bytes or 2.45% below ordinary level-1 Zstandard. Against level-1 Zstandard in the same split aperture layout, packing saved **101.28 ms** on the paired joint clock. [Machine receipt](measurements/ci16-packed-storage-0016.json.gz)

| Capture layout | Capture write, wall / CPU | First mixed use, wall / CPU | Joint clock, wall / CPU | Stored bytes |
|---|---:|---:|---:|---:|
| Ordinary Zstandard level 1 | 153.54 / 153.54 ms | 289.59 / 289.58 ms | 444.30 / 444.29 ms | 78,731,276 |
| Aperture-split Zstandard level 1 | 187.14 / 187.08 ms | 255.87 / 255.86 ms | 443.77 / 443.71 ms | 78,753,870 |
| Aperture-split measured-width CI16 | 123.63 / 123.58 ms | 217.65 / 217.65 ms | 342.49 / 342.43 ms | 76,799,710 |

The table gives medians by scope. Paired clock savings compare layouts within the same order. The initial three-order run also saved a median 106.10 ms wall, with the same byte and science evidence. The final run includes the aligned-input guard and an actual first mixed analysis of the legacy conversion.

## Codec and verification

The 51.2 million original signed words ranged from −2048 to 2047. In the 128 physical aperture blocks, 124 needed 12 signed bits and four needed 11. The measured common shift was zero in every block. The writer measures every block before packing. A two-byte header commits width and shift. The SSSE3 path packs eight 12-bit words at a time, and the scalar path handles other measurable widths and remainders. Full-width data retains its CI16 words. Synthetic tests cover left alignment, full-range input, signed extremes, unaligned buffers, padding, truncation and a corrupt unused tail. [Native implementation](ci16_packing.c) · [Codec binding](ci16_packing.py)

Ordinary capture reproduced the original compressed member SHA-256. Packed capture authenticated all 128 encoded blocks on first use, including unused tails. It decoded 60.8 MB, versus 102.4 MB in ordinary analysis. All layouts preserved the signed index and the complete ordered timeline and detector probe digests, with 64 issued visits, 58 admitted, eight full stereo anchors, 50 short stereo primaries and 45 factors. A separate full readback of every layout recovered all 102.4 MB of original CI16. [Frozen protocol](ci16-packed-storage-protocol.md)

The first-use reader loaded every stored byte, so the 1.93 MB size saving applies on both the write and read side. Under a simple serial transfer model, the measured 103.37 ms local saving plus 3.86 MB less transfer gives about **122.7 ms** at equal 200 MB/s read and write rates. The test timed one CPU 2 worker on tmpfs. The capture, first-use and legacy clocks had zero input blocks, and no original backing-storage or RF collection occurred. The dependency setup, which recorded 64 process input blocks, and the decode that hydrated the verified fixture sat outside the measured capture clocks.

## Legacy conversion

On the same ordinary member, the conversion took 191.14 ms wall. Its actual first mixed analysis took 215.16 ms and independently reproduced the original receiver evidence. Full sidecar readback cost another 167.70 ms and recovered the original raw SHA-256. Relative to the 289.59 ms ordinary analysis median, this one-member warm cost model recovers conversion plus readback on the **fifth mixed analysis**. Retaining the original adds 76,803,294 sidecar bytes. The measurement retains the original archive and uses one member. [Run harness](ci16_packed_storage_trial.py)

Twenty-three component and regression tests passed across the scalar and SSSE3 paths. The layout remains private to this experiment. [Tests](../../../tests/pipeline_eval/test_ci16_packing.py)
