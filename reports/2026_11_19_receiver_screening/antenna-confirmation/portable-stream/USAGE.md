# Run conditional antenna acquisition from saved I/Q

The application accepts the same native 10 MS/s dual-antenna manifests, causal TLE archive, track configuration and search region as the stock saved-I/Q receiver. It requires x86-64 Linux, system FFTW and the Python packages in the archive’s `requirements.txt`.

```sh
sha256sum -c SHA256SUMS
tar -xzf portable-antenna-receiver.tar.gz
python -IB portable-receiver/receive.py capture-input.json --out result \
  --detector partner-on-hit --visit-workers 2 --cpus 0 1
```

Choose two CPU IDs available on the host and a new local output directory. The receiver alternates its primary antenna on successive valid visits to each RF centre. In `partner-on-hit` mode it computes the partner on a positive primary fractional gate. In `second-on-miss` mode it computes the partner on a negative gate. The default stock detector uses both antennas at every visit. Use one or two visit workers with either conditional mode. Each worker owns a native detector context. The reader commits results in the original arrival order, with at most two visits in flight.

The normal outputs include `native.json`, both geographic and frequency fits in `position.json`, and the measured service resources. Each valid visit’s conditional ledger records its physical primary, partner decision, detector thread CPU and wall time. Hardware exclusions remain in the native document. The hit-mode identity binds its policy, detector binary, capture manifest, measured probe arrays and exclusions. The application reads no reference position, stock detector output or precomputed antenna schedule.
