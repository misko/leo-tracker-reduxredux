# Run the receiver from saved I/Q

Verify and unpack `portable-receiver-conditional.tar.gz` into a new directory. Use the supplied Python requirements from the package, a compatible x86-64 Linux host and the system FFTW library. Existing stock portable manifests work directly. [Stock input format and operating environment](../../latency-and-support/portable-receiver/USAGE.md)

```sh
sha256sum -c SHA256SUMS
tar -xzf portable-receiver-conditional.tar.gz
python -IB portable-receiver/receive.py capture-input.json --out conditional-result \
  --detector second-on-miss
```

Omit `--detector` or use `--detector stock` for full stock. The conditional mode uses the first CPU in `--cpus FIRST SECOND` for chronological acquisition replay and the same phase-release position stage. Stock uses both CPU slots for independent segment lanes. The current common entry checks that both IDs exist. The app accepts complete schema-v2 10 MS/s dual-RX captures with 20 ms visits, a readable causal TLE archive, the original tracking configuration and an explicit 25 km search offer. The bundle does not require a checkout or a database. You can run it as any account with read access to the capture assets and permission to create the output directory.

`native.json` preserves both physical probe slots and all acquisition clocks. A gated primary leaves the alternate slot empty. A miss invokes the same stock library on the other physical antenna. The primary alternates on each recorded integer RF center and invalid visits do not advance the schedule. `conditional-visits.jsonl` records the actual dispatch and detector-call timing on valid visits. `position.json` contains `c0` and `fitted_c`. Treat these optional-mode results as a speed and accuracy tradeoff on the captured signal, with no new hardware acquisition claim.
