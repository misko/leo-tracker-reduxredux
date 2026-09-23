# Synthetic phase-geometry observability

`simulate.py` generates `results.json` from explicit simulated truth. It reads
no IQ, orbit catalogue, station measurement, or QNAP path. The calculation is
used by the accompanying audit to show rank after nuisance treatment, not to
estimate any property of the station or a satellite.

```sh
uv run --no-project --with numpy python \
  reports/figures/2026_09_23_phase_geometry_observability/simulate.py
```
