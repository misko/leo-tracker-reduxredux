# Inference input audit

The localization prior is a 25 × 25 km square centered at **37.906°, −122.545°**.
The 10 km mapping disk uses the same center. The supplied ground-truth GPS
coordinate is a postfit evaluation value, not an initialization or box center.

The older research tools had two dependencies that needed clearer treatment:

- Later correction experiments inherited algorithm-selected labels, aliases,
  calibration and positions from earlier fits of the same scan. Their surfaces
  were conditional on those choices, rather than fresh regional discovery.
- The older orbital-history exporter extracted past records from a combined
  history/following-TLE diagnostic and covered a subset of candidate satellites.
  The current inference path no longer reads that diagnostic or subset export.

The new branch generates eight radio proposals from zero, searches all eligible
regional candidates, retains distinct data-generated modes, and refreshes
assignments at 25 regional grid nodes. Each configuration chooses a branch by
its c0 objective. Matched c0/fitted-c arms use that common branch and primary
search starts. There is no manually supplied satellite-ID list or saved fit.

| Input | Current use | Outside current scan's RF? |
| --- | --- | --- |
| Graph CFO points and polynomial partition | Original observations; radio-only partition hashes verified | No |
| GLRT300 CFO remeasurement | Archived pilot evidence; no new RF collection | No |
| Noise scales | Same-scan radio polynomial/pilot features | No |
| Frame links | Same-scan timing pairs, not earlier fitted clock coefficients | No |
| Satellite labels/aliases | Generated anew from the full regional bank | No |
| Nominal/previous TLE | Element epoch and actual archive collection before pre-scan cutoff | Yes: causal orbital information |
| Orbital-history means | Available verified causal catalogue records for every regional candidate | Yes: causal orbital history |
| RX/band offsets and drift | Fitted from the current scan's curved evidence | No |
| Linear-track geometry | Nominated from the fresh current-scan curved solution; cannot calibrate hardware | No |
| Regional center and model scales | Declared geographic/engineering assumptions | Yes: regional prior and fixed model settings |
| Ground-truth GPS | Report marker and position-error calculation after inference | Evaluation only |
| Following TLEs, pooled RF/site estimates, old endpoints/seed files | Rejected by runtime read guard in the new branch | Excluded |

The bank itself uses a broad 250 km visibility prior around 37.5°, −122.0°,
including a generous below-horizon guard, and restricts the model universe to
Starlink names. These assumptions do not select satellites by observed GPS or
an association result. The 25 km search square lies inside that bank region.

Nominal element text is reconstructed in bank order and bound to its original
hash. Each record needs both its epoch and collection time before the cutoff;
an old epoch in a later-downloaded record does not establish causality. The
previous catalogue is separately hash/provenance checked. Published historical
following-TLE diagnostics are preserved, but not used in new inference.

The nominal loader now requires `nominal_elements.json` for the requested scan,
and rejects a missing file, another scan's metadata or an incomplete candidate
set. The original multi-scan container was explicitly indexed by scan and all
selected records were causal; the final isolated files additionally prevent
inference from opening later scans' catalogues. Initial read receipts remain
unchanged, and all endpoints are replayed with the isolated records.

The service archive cannot be read by this session. The complete candidate
histories therefore use the verified causal exports available locally. They
cover every regional candidate but have incomplete historical depth. Earlier
scan exports contribute only orbital records available before the current
cutoff; no earlier scan's RF, calibration or position estimate is transferred.

The old utility module `analyze_dsx01_fixed_site` exposes evaluation latitude
and longitude globals, and some imported reporting modules expose `REFERENCE`.
The called statistics/propagation functions receive their geometry explicitly.
The adversarial [GPS invariance check](gps_invariance.json) changes imported
evaluation constants to Sydney, reruns fresh discovery and 152 objective
evaluations, and records whether they change. This supplements source review
and actual file-read receipts; it is not a universal noninterference proof.

**Remaining limits:** the assignment search is finite and heuristic. Plots hold
the selected assignment branch fixed while evaluating location; they do not
marginalize every possible identity and alias at every pixel. The imported
priors and thresholds were developed on DSX01, so this remains development-data
evaluation rather than independent validation at a new location. Loss values
from different likelihood-power designs cannot be ranked as model probabilities.
