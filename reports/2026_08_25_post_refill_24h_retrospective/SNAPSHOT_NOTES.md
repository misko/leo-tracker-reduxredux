# Archived-code provenance notes

The report bundle was assembled from a dirty research worktree. The objective
is to retain enough source material for later forensic inspection, even when a
script is not expected to run in a future environment.

## What is archived

`code/snapshot/repository/` contains every known satellite-activity tool,
research component, owned test, and calibration/corpus helper used by the
published reports that was not tracked by Git when this bundle was created.
`code/snapshot/visualization/` contains seven ad-hoc builders from the Codex
visualization workspace, including the 115401 and 135219 builders. Exact source
hashes and original paths are in `code/SNAPSHOT_MANIFEST.json`.

Git-tracked contracts, sky propagation modules, `pyproject.toml`, and `uv.lock`
are not duplicated. They are bound to repository commit
`5e756eb3b1d0ecf9b806d9e4b2a5824cc0175d9c` and separately SHA-256 hashed in
the manifest.

## Historical byte drift

Some report artifacts were produced before later backward-compatible research
extensions changed the untracked source files. The current versions are
archived because the earlier bytes are no longer present in the worktree. The
artifacts themselves preserve the exact historical hashes:

| Historical artifact family | Path | Artifact-bound SHA-256 | Archived current SHA-256 |
|---|---|---|---|
| 085623/103607 multipath | `src/leo/analysis/research/joint_multipath_satellite_activity.py` | `140368215793b67a8345ed215e512a7c582920d3437a813bca12294d40205510` | `d2b6b0a8e80239e5e1e6f3234e5a6585ce28d936a97981642a666857fa3bd31a` |
| 085623/103607 multipath | `src/leo/analysis/research/multi_satellite_activity.py` | `90d2811f29ca9f4a1dcd93baff791b5f3fa3655eceabdfac4fea00618999c7fc` | `bc57b3bb29c226c281877380d167cd605ba8e68b64bd8ab55884decb5faccf3d` |
| 085623/103607 multipath | `src/leo/analysis/research/multipath_satellite_activity.py` | `86c677c18518b440524f7aede518c453790a94e4d4f75bacf64038218d47af94` | `c8e2a1eb514519b6ed3915e0ad5dc43980ae62eb03eda3973fec5a442120f9fb` |
| 085623/103607 multipath | `src/leo/analysis/research/satellite_activity.py` | `641d24a0aa85cf0290409da3cdad67fb03ecd06cd8145aacd707d01d3f86448f` | `0bc9d84fa669bdc4e7efefa07d5495d49b8048aa840d45ebb352918cdeda0d7d` |
| 085623/103607 multipath | `tools/replay_raw_multipath_satellite_activity.py` | `5bab2c46612939bc2b06406533bbaf29092b9266b2196e5031b9e5474a1df692` | `9a498cc2ceff389c70e268d280555e0102d885a356435d70fc5046b8a55ebe53` |
| Final 085623/103607 fixed-target controls | `tools/replay_raw_single_path_fixed_norad_paired_prediction_time_specificity.py` | `9556fe8f7741abdb733e0c09c5420cd775203021405d21618f3fcd2fe94a41b8` | `f8ed3732ef78ae724e47370f4c5d3e501eb44f80cdec02483d2e2312897939e4` |

For the historical multipath artifacts, 12 of 17 bound implementation files
still match byte-for-byte. For each fixed-target control artifact, 20 of 21
bound files still match; the one later change was in its wrapper. No output was
silently regenerated with the newer bytes.

The 073628 exhaustive-fine artifact and the early 065355 branch replays predate
the complete producer-manifest convention. Their outputs and command recipes
remain preserved, and the current report-only implementations are archived,
but exact source-byte identity cannot be asserted retrospectively.
