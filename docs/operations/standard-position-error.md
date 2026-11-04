# Final position error on standard figures

The `final-error-v7` presentation displays both fitted-c and c=0 geographic
errors prominently above the map. The distance is measured from the published
endpoint to a user-confirmed evaluation site, never to the regional search
centre. Without a confirmed site it explicitly reports unavailable error.

The presentation worker accepts `--evaluation-latitude` and
`--evaluation-longitude`. These flags are presentation-only: the scientific
terminal is already complete before they are used. A per-recording reference
is attached through the public store after publication. Existing per-recording
references take precedence over the current service setting. Normal background
publication does not attach the current site to historical completed scans.
Use an explicit `--run-id` to upgrade a known historical scan. Old PNG digests,
manifests, grids and paths remain readable under their original revisions.

On November 4 the user confirmed 37.849061591561885, -122.48574968092912 for
the 14:00:48 UTC scan and new scans until further notice. When the receiver
moves, change/remove these flags before publishing scans at the new site.
This is an evaluation convention, not an assumption used by localization.

`tools/profile_algo07_publication.py` reconstructs a completed job's predictions,
conditional grid and eight figures into a new private store. It profiles evidence
validation, reconstruction, plotting and file publication; preserves the public
terminal binding; and separately reports the recorded ALGO02–07 worker times.
Run it with the installed numerical Python, one BLAS thread and an external
timeout of at most 30 minutes. Its timings include cProfile overhead. It does
not rerun acquisition, GLRT or position optimization, and does not publish into
production. Do not sum fresh replay times and historical worker times and call
that a measured end-to-end pipeline run.
