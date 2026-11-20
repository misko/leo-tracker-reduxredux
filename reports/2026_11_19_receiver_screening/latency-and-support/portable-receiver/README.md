# Run stock wide GLRT and compact position from saved IQ

The portable receiver accepts explicit saved-capture manifests, a causal TLE archive, a track configuration and an offered region. Its single entry runs the stock wide detector and returns both compact calibration arms. For DS26-0197, the relocated program reproduced the complete 23,962,057-byte native document exactly. The canonical position output matched the archived receiver after removing only the stage timings. [Download the application bundle](portable-receiver.tar.gz) · [Usage and input format](USAGE.md) · [Both-arm charts](charts/index.html)

```sh
python -IB /path/to/portable-receiver/receive.py /path/to/my-input.json \
  --out /path/to/new-results
```

The complete replay authenticated **6,772 visits** in 14 segments, including 11 invalid hardware visits, and read 106 compressed chunks. It ran from a different working directory after moving its application directory. The qualification used a fresh wheel-only Python environment, hid the source checkout and installed capture producer, and isolated networking. On user-readable input, the entry uses ordinary file permissions. Its qualification service used the existing archive reader account for this protected recording. Two early permission rejections stopped before IQ processing and are preserved separately. [Explicit fixture manifest](recording-input.json) · [Service proof](service.json) · [Source and scope](source-lock.json)

| Measured phase | Seconds |
|---|---:|
| Two-lane authenticated raw detector | 108.28 |
| Native factor assembly | 0.80 |
| Relocated backend binding | 0.68 |
| Compact solve | 69.31 |
| Complete service | 179.52 |

The real cgroup peaked at **512 MiB** with zero swap and used 268.64 CPU seconds. The detector and position measurements cover the saved-IQ host replay. The 201 application files total 5,109,596 bytes, and the downloadable bundle is 1,604,335 bytes. The separately installed Python wheel dependencies occupied 278,406,755 bytes in the qualification environment. The deployable bundle targets the measured x86-64 Linux ABI, uses the system FFTW library and checks the exact SciPy LP64 provider. Captures and the causal archive stay external. [Deployment and phase measurements](deployment-proof.json) · [Package checksum](package-lock.json) · [Python dependencies](requirements.txt)

| Arm | Compact error, km | Compact conditional RMS, Hz | Original v5 error, km |
|---|---:|---:|---:|
| c = 0 | 0.792 | 80.52 | 0.528 |
| fitted c | 0.992 | 80.56 | 0.689 |

The four distinct original v5 curves use capture-era data and have coincident positions within each arm on this recording. This single recording verifies deployment parity with the stock compact receiver. [Position and RF scores](position-scores.csv) · [Prediction lock](prediction-lock.json)
