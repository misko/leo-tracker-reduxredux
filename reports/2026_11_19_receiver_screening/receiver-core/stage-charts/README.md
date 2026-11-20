# Receiver-core detector and acquisition stages

[Combined PDF](stage-evidence.pdf) · [Source and artifact hashes](manifest.json)

Each page links measured data for one detector or timing change. Matched native x86 and Cortex-A9 QEMU timings appear on separate pages.

- Reuse exact Lanczos coefficients · [PNG](screened-lanczos.png) · [CSV](screened-lanczos.csv)
- Paired integer-VNNI epochs · [PNG](screened-vnni.png) · [CSV](screened-vnni.csv)
- CFO stride on the x86 host · [PNG](cfo-stride-host.png) · [CSV](cfo-stride-host.csv)
- Pilot epoch carry across retunes · [PNG](epoch-carry.png) · [CSV](epoch-carry.csv)
- CFO-invariant pilot power envelope · [PNG](amplitude-envelope.png) · [CSV](amplitude-envelope.csv)
- Complete-epoch 18-tap proposal · [PNG](complete-epoch-proxy.png) · [CSV](complete-epoch-proxy.csv)
- CFO stride under Cortex-A9 emulation · [PNG](cfo-stride-cortex-a9.png) · [CSV](cfo-stride-cortex-a9.csv)
- Predict the next pilot epoch on a Doppler track · [PNG](track-timing.png) · [CSV](track-timing.csv)
- Causal scout starts from earlier tracklets · [PNG](causal-track-scout.png) · [CSV](causal-track-scout.csv)
- Use a causal hint in the four-start GLRT · [PNG](hinted-glrt.png) · [CSV](hinted-glrt.csv)
- Held pilot epochs and predicted orbital range · [PNG](range-epoch.png) · [CSV](range-epoch.csv)

[Long-form values for the paired detector charts](measurements.csv)
