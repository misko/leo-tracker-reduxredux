# Five late September 24 dual-RX tracks

`selection.json` freezes five exact dual-receiver track pairs before the phase
outcomes are assessed. `summary.json` contains the resulting per-dwell metrics.
The three PNG files visualize coverage and controls, held residual phase, and
the candidate-orbit geometric envelope.

The analysis requires read-only access to `/srv/bulk/leo` and `/var/lib/leo/tle`.
From the repository root:

```bash
.venv/bin/pytest -q tests/tools/test_report_late_dual_rx_track_phase.py
.venv/bin/ruff check tools/report_late_dual_rx_track_phase.py tests/tools/test_report_late_dual_rx_track_phase.py
mkdir -p /tmp/late-dual-rx-track-phase-20260924
chmod 0777 /tmp/late-dual-rx-track-phase-20260924
sudo -u leo env HOME=/tmp MPLCONFIGDIR=/tmp/matplotlib \
  PYTHONPATH="$PWD/src:$PWD" \
  "$PWD/.venv/bin/python" "$PWD/tools/report_late_dual_rx_track_phase.py" \
  --output /tmp/late-dual-rx-track-phase-20260924
cp /tmp/late-dual-rx-track-phase-20260924/{summary.json,coverage-and-stability.png,held-phase-traces.png,candidate-phase-change-comparison.png} \
  reports/figures/2026_09_24_late_dual_rx_track_phase/
```

The selection is phase-blind. The phase method uses deterministic random groups
within each dwell and no chronological holdout. Catalogue associations remain
candidate-only, and the 8 cm result is an orientation-maximized mechanical
baseline envelope rather than a calibrated geometric prediction.
