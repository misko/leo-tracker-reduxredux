# C adaptive geographic release: qualification and next screen

This fitted-c-only prototype leaves the original objective, candidate bank,
physical prior, six original starts and original results unchanged. Each original
fit remains eligible only when its original receipt is stationary and independent
physical objective/NLL/full-KKT replay agrees. Every original endpoint is retained
in the eligibility inventory, including failed and nonstationary endpoints.

The trigger is the already prespecified geographic screen: original full KKT at
most .001 with saved/replayed agreement within 1e-7; radius within 1e-6 km of
25 km and disk-constraint slack at most 1e-6 km²; outward radial derivative at
most -.01 objective/km; and centered 0.1 m derivative negative and agreeing within
max(.005 objective/km, 1% of the analytic derivative). The physical descent
threshold is separate from the differently scaled KKT threshold.

The new `adaptive_geographic_disk.release` port permits exactly one additional
20-second/600-iteration fitted-c call per independently qualifying original start.
It centers a new 25 km disk on that endpoint and passes the exact saved physical
vector and nuisance to the unchanged fitter. The first seven coordinates must
remain identical; the existing at-most-1e-8 timing-face initializer margin is
permitted only when old/new domains produce bit-identical effective starts. No
recursive release, clipping, relifting, reference seed, extra incumbent, likelihood
change or retry is permitted. Expected failures are retained; unexpected failures
propagate. A future live receipt owner must exclusively claim each original start
before invoking this port. This command does not launch live release fits.

Selection minimizes training objective over independently accepted stationary
original and released endpoints, then original start index, then original before
release for exact ties. Reference and held data are absent from screening and
selection. There can be at most six added calls (120 optimizer seconds) per case;
this is explicit extra optimization budget, not a budget-matched original run.

Retrospective mechanism qualification carries the exact two already sealed
releases: before031 cold-1 and after003 shape-high. The all-six audit found no
other trigger among those cases or negative interior after023. It independently
rechecks all 18 originals, carried call options, exact raw/effective seeds,
source physical endpoint and returned objective/NLL/full KKT. It launches zero
new fits. The relevant original cost is 18 original C-all calls plus two carried
policy release calls. Four other already performed mechanism controls are
incidental and counted separately; original full case pipelines and discovery
costs also remain separate. This is retrospective mechanism qualification, not
new independent accuracy validation or blanket promotion.

The next prospective zero-fit screen includes every genuine C-all endpoint from
before029, before037 and after029. The large configured errors motivated these
cases before this screen; neither errors nor half-view winners enter the trigger.
Half selections need not exist. Source/cohort identities, original physical
initializations and all six calls are checked through the original cached parent
ports. No automatic fit follows this screen: publish trigger counts and a concrete
bounded next-call protocol for review first.

`tools/ds21_model_c_adaptive_disk_release.py` provides `freeze-screen`,
`freeze-qualify`, and `run`. All source/input authorities and original receipts are
bound before cache preparation. Frozen sources are archived; original parent
validation runs before preparation and bindings are rechecked before terminal
publication. Both three-case operations include preparation and evaluation in a
180-second internal bound, external TERM at 195 seconds and KILL at 200 seconds.
Each namespace is fresh and immutable, and an existing launch forbids retry.

Concrete next parents under `reports/2026_10_14_ds21_ds22_next_round/local`:

- `model-a-pipeline-before-029-cached-v2`
- `model-a-pipeline-before-037-cached-v2`
- `model-a-pipeline-coverage-029-cached-v2`

Concrete mechanism parents in order: `model-a-pipeline-before-031-cached-v2`,
`model-a-pipeline-coverage-003-cached-v2`,
`model-a-pipeline-coverage-023-cached-v2`. Carried controls in order:
`model-c-domain-before-031-control-v1`, `model-c-domain-control-v1`.
