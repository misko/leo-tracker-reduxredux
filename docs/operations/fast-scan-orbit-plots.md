# Standard fast-scan orbit plots

The full standard fast-analysis pipeline publishes four PNGs after the saved
Hard60 regional result is available: `ch1-4-all`, `ch5-8-all`,
`ch1-4-unassociated`, and `ch5-8-unassociated`. Every panel spans 0–300 seconds,
including empty receiver/channel lanes. Both receivers have separate panels.
All selected fitted-c satellites are drawn in every channel at that channel's
recorded RF, with horizon gaps and alias discontinuities preserved.

The plots use the original top-one passing GLRT windows used by the regional
model. They do not include skipped fast-score windows or create new detections.
Receiver calibration is removed from the points; orbit timing and any published
satellite frequency corrections remain in the predictions. Values are wrapped
at the GLRT alias period. No fitting or RF collection runs during rendering.

Unassociated means the selected model's clutter posterior is at least as large
as every individual satellite posterior. This is a presentation classification,
not the frozen bootstrap association count. The same classification and curves
are used in all four plots. The replayed likelihood must reproduce the saved
likelihood before publishing. This is an in-sample diagnostic and establishes
neither satellite identity nor better localization. Existing controlled zero-c
versus fitted-c positioning comparisons are retained without rerunning search.

PNGs and their provenance live in the new `fast-scan-orbits-v1` namespace through
`FastScanStore`; historical persisted products are unchanged. The web UI polls
`/api/v1/fast-scans/{run_id}/orbits` and displays/downloads the PNGs from
`/api/v1/fast-scans/{run_id}/orbits/{name}.png`. The manifest records input,
analysis, selection and TLE digests, satellite inventory, observation counts,
classification and frequency conventions. Missing selection is explicitly
reported on empty figures. Publication failures prevent automatic completion.

To backfill a completed scan, run in the selected standard worker environment:

```sh
standard-python tools/fast_scan_orbit_plots.py \
  --input /srv/bulk/leo/fast-scan-tracking-inputs/RUN_ID.json \
  --output /srv/bulk/leo --tle-root /var/lib/leo/tle \
  --run-id RUN_ID --title RECORDING_ID
```

The worker must include the current `orbit_plot`, `fast_scan_orbits`,
`contracts.fast_scan_orbits` and `storage.fast_scan` modules. Use the published
input's provenance run ID; the recording name and tracking session ID differ.
Existing immutable publications are verified and reused. Backfill is bounded to
selected-satellite propagation, with a 60-second propagation limit, plus rendering.

## Live publication on 2026-10-16

The release is `/opt/leo-fast-orbits/20261016-r1`. Its web build uses the deployed
shared-scan UI source plus the orbit panel, preserving other deployed views.
The API override is
`/etc/systemd/system/leo-api.service.d/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-fast-orbits.conf`.
The existing standard script entry point forwards future slices to this release;
the analysis watcher and already running slices were left running. The original
script is saved as `previous-standard-script.py` in the release for rollback.
To roll back, restore that script to
`/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py`, remove only
the orbit API override, reload systemd and restart `leo-api`.

The example `fast8-auto-20261016-121333-6492cd66-1-lower` was backfilled and
validated through the full standard entry point with all stages, including
`orbit_plots`, complete. Its saved B7 likelihood was reproduced within 1e-5;
4,549 observations yielded 2,739 posterior associations and 1,810 unassociated
windows across 33 selected satellites. The live API served all four PNGs and
the browser displayed their panel.
