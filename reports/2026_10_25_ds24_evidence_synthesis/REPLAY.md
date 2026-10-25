This compact retrospective preserves its narrative, exact plotted values, three
PNG/PDF figure pairs, rendering source and hash-bound RF checkpoints. It adds no
position fits, observations, source assignments or operational policy.

[figure_data.json](figure_data.json) lists the historical summary paths and their
SHA-256 hashes. The report links the corresponding published studies. Those
external research inputs are not copied here; this directory is not a standalone
scientific-input or runtime archive. The current parent-uncertainty checkpoint is
RF-only. Its separate experiment report owns endpoint replay and geographic
evaluation.

To regenerate the figures in the original research environment, restore the
exact summary files at the paths listed in `figure_data.json`, verify their
hashes, and run `python make_figures.py` with NumPy and Matplotlib installed.
The script performs no inference. Font/library versions may change rendered
bytes; the committed images and PDFs are the reviewed presentation artifacts.
The numeric checkpoint JSONs remain the source of the quoted values.

[publication_manifest.json](publication_manifest.json) records the exact compact
published files. It excludes itself. No release assets or new RF data accompany
this review.
