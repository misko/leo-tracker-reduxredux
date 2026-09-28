# DS7 evaluation preparation

Prepared from the exact frozen DS7 manifest. No scientific model evaluations or IQ processing were launched by this setup.

| Artifact | Scope |
|---|---|
| [Smoke plan](plans/smoke/plan.json) | First recording; 1 unit |
| [Standard plan](plans/standard/plan.json) | 88 singles, eleven groups of eight, full88; 100 units |
| [Budget plan](plans/budgets/plan.json) | Standard plus two/four-recording prefixes; 122 units |

Each plan is content-sealed and contains only allowlisted model-facing metadata. Its adjacent `inputs.template.json` marks every recording unavailable until a model-owned observation export is audited and frozen. Copy the template to a working input index; do not treat it as an available analysis product.

The shared [workflow](../../docs/research/ds7-evaluation.md) describes loading, input freezing, adapter execution and post-seal scoring. The [SOL launch plan](../../docs/research/ds7-parallel-plan.md) assigns six directions in dependency-aware waves of at most three workers.

The six [research arm configurations](../../config/ds7/) remain planned; the position-aggregation control adapter is implemented. Transport tests use synthetic positions and do not constitute DS7 localization results.

Validation: DS7 metadata inspection and all three plan preparations passed. The component suite covers metadata/input/run tampering, deterministic unit plans, source-reader bindings, response accounting, subprocess execution/timeouts, unavailable inputs, scoring denominators, and aggregation controls. See `tests/research/test_ds7_eval.py` for the executable checks.
