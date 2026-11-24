# Physical DS30-0107 strict packed transfer and two-case result

The same strict 20/8 history and Cairo CLI withheld on the complete physical DS30-0107 recording in **0.542 s** including derivative setup, compared with **1.497 s** for installed ALGO08v3. Charging the earlier measured conversion and independent readback brought first use to **0.861 s**. Both arms were null at `no_active_curvature`, and no position, grid, path or PNGs were published. The CLI used the same Cairo option as DS30-0016 and reached the verified early exit before importing the scientific solver or renderer. [Positive physical case](strict-cairo-0016.md) · [Protocol](strict-cairo-0107-protocol.md)

| DS30-0107 timing boundary | Elapsed s | CPU s | Elapsed speedup vs installed |
| --- | ---: | ---: | ---: |
| Measured installed ALGO08v3, original stage | 1.497 | 1.496 | 1.000× |
| Measured history and Cairo, original stage | 0.540 | 0.539 | 2.770× |
| Strict packed history and Cairo child | 0.535 | 0.534 | 2.797× |
| Strict packed child plus derivative setup | 0.542 | 0.540 | 2.764× |
| Strict packed first use with conversion and independent readback | 0.861 | 0.859 | 1.739× |

The reused qualified private derivative retained the 29 original signed windows, including a cancelled 136,857-sample extent and a zero-sample capacity skip. Its earlier 0.319 s conversion included 0.058 s to build the codec, 0.216 s for authenticated conversion and 0.041 s for independent full decoded readback. The current process paid 0.006 s in derivative setup and 0.119 s in authenticated raw acquisition. Common setup and reference validation took a separate 0.063 s. Including common setup yields 0.605 s prepared and 0.924 s first use. The strict and original-input Cairo child times differed by 5 ms on single launches, and by about 1 ms in the opposite direction after charging derivative setup. The principal tiny-case improvement comes from the exact early withholding path already present on original input. [Derivative qualification](strict-packed-0107.md) · [Original-input Cairo control](history-risk-0107-cairo.md)

The installed and strict publications preserved all 54 original stereo-lane opportunities and the two original exclusions. The strict run reproduced the qualified Cairo native packet with all 19 signed factors and the exact graph proof, null calibration arms and terminal. The published candidate scan bytes matched the original-input candidate. Installed v3 retained the same signed opportunity counts. The packed acquisition authenticated 33,221,254 encoded B in 58 block commitments and decoded 24,960,000 B across eight full and 19 short stereo visits. The derivative's 8,136 pages stayed resident, the child had zero input blocks and zero major faults, and the reader recorded zero original waveform windows and no fallback. Both inputs were verified tmpfs and no original backing files were accessed.

## DS30-0107 and DS30-0016

| Same candidate boundary across both cases | Median paired candidate/installed | Summed candidate/installed | Median speedup | Summed speedup |
| --- | ---: | ---: | ---: | ---: |
| Raw child through exit | 0.482 | 0.577 | 2.073× | 1.734× |
| Prepared, including candidate-specific setup | 0.485 | 0.579 | 2.060× | 1.728× |
| Prepared with common custody and setup | 0.509 | 0.588 | 1.966× | 1.702× |
| First use, conversion and full independent readback included | 0.824 | 1.012 | 1.214× | 0.988× |
| First use with common custody and setup | 0.847 | 1.021 | 1.181× | 0.980× |

Both prepared ratios pass the 1.6× gate even after common setup is charged to the candidate. The summed clock exceeds the 2× gate. Both first-use ratios miss 1.6×. The two installed denominators are actual previous raw through-exit measurements on the same staged originals. The two recordings provide one verified positive and one exact early withholding. They do not establish a population speedup or a deployment result.

## Reproduction

The command, signed controls and charged scopes were frozen in `c8382126d`. Invoke `strict_cairo_0107.py run /dev/shm/leo-v3-strict-cairo-0107-result01` as `leo` through the release interpreter under the shared Gauss lock, one numerical thread, CPU 2, nice 15 and I/O priority 7. Bind the verified original tmpfs recording as a read-only mount at its canonical recording name in a private namespace. The pinned derivative, codec, map and independent original verification receipt are read from the prior strict tiny result. Run `score` with the same output directory and checkout `src` available for product verification. The score binds the actual CLI command, original and derivative residency and signed inventory, both control clocks, conversion costs, scan and withheld terminal, and the two-case accounting. The unpacked score SHA-256 is `c99ef65d377f208c9c646d7872ca5bfeb3a7d537c73faffadd77f2ddfc0b411a`.

[Runner](strict_cairo_0107.py) · [Sealed score](measurements/strict-cairo-0107.json.gz)
