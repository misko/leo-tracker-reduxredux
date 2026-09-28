# Validation and execution notes

The full-calibration and shared causal/joint-fit component suite passed 19 tests.
The DS8 cache component suite passed five tests. The final DS8 scorer and snapshot
authority suites passed seven tests; Ruff passed for their sources and tests.
These are focused component checks, not a repository-wide test result.

Independent audits are retained in `audit-models.json`,
`audit-snapshot-authority.json`, and `cache-audit.json`. The model audit recomputed
all 16 optimizer objectives and selections. The cache audit checked all four fixed
members and found no cross-role overlaps in either window times or source-support
metadata. The snapshot audit reconstructed the public API's causal selection rule.

The first mapping launcher attempt failed before starting the numerical subprocess:
the completed candidate bank had root-only read permissions. The empty receipt was
preserved as `mapping-preflight-empty.json`; local read permission was added to the
bank without changing its contents. The unchanged launcher was then invoked with
the same protocol, inputs and numerical settings. Subsequent local stage outputs
may receive the same read-permission correction before dependent stages run.

Each numerical stage records its command, source/input hashes, terminal output,
resource use and exit code. The fixed protocol and launcher remain unchanged.

The completed result audit (`audit-results.json`) passed per-window to role sums,
common control-reference checks, all 102 equal-record aggregations and source
bindings. It independently reconciled 1,767 unique selected-lane windows against
3,551 reception/later partition windows: 1,784 are outside selected lanes, with
no missing window within a selected lane. All eight numerical stage exits are
zero; a final root check verified all 58 current stage launch hash bindings.
