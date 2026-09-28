# Optimized persistent worker

Build the persistent saved-IQ worker from the qualified `rankconversion`
snapshot without touching the frozen concurrent artifacts:

```sh
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/build_worker.py rankconversion
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/build_worker.py rankunroll --recorded-arrivals
```

Validate a phase locally without connecting to the target:

```sh
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py trial --validate-only
```

The live commands for the serialized operator are:

```sh
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py glrt-only
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py combined --capture
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py combined-irq1 --capture --irq1
python3 reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py cadence --candidate rankunroll --recorded-arrivals --jobs 330 --seconds 60 --capture --irq1
```

Each phase stages the hash-named optimized executable, creates a unique local
and target phase directory, and records the exact binary and source receipts.
`--irq1` discovers the sole `eth0` IRQ, pins it to CPU1, and restores and
verifies its original mask in `finally`, including phase and pin failures.
Recorded-arrival phases use a separate `*-cadence-arm` executable built from
the frozen `paced.c`, include the schedule hash in `run.json`, and use an
`opt-CANDIDATE-recorded-*` namespace.
