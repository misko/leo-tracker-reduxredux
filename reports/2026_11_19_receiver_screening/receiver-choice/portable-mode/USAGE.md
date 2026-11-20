# Portable saved-IQ receiver with optional staggered detection

Install the included Python requirements from local wheels using CPython 3.12. The application uses x86-64 Linux and system libfftw3.so.3. The portable bundle checks the qualified SciPy LP64 provider.

Use the same complete v2 dual-RX capture, SHA-256-bound manifest and causal archive as the stock portable receiver. The included example-input.json shows paths and digest fields. Both modes feed the same compact localization backend. Choose two available CPUs for the raw worker. Staggered uses the second CPU for its persistent native detector helper. The first CPU also runs the position fit.

```sh
# Existing manifests default to stock.
python -IB /path/to/portable-receiver/receive.py my-input.json --out stock-result

# The optional detector uses one fifth-center search per valid visit.
python -IB /path/to/portable-receiver/receive.py my-input.json \
  --detector staggered --cpus 6 7 --out staggered-result
```

Provide read permission for the saved source and write permission for a separate output directory. Source paths are resolved relative to the input manifest if needed. The application writes the numerical prediction to position.json, both calibration arms, and the local native handoff and receipts. Staggered additionally records the selected receiver and exact target RF in staggered-visits.jsonl. The application package contains no capture payloads.
