# Generic recovery coverage

All193 members are accounted for. Partial progress is diagnostic; full-cohort position metrics remain withheld until full terminal and matched-position coverage.

| Dataset | Members | Terminal | Matched fitted-c positions | Matched c=0 positions |
|---|---:|---:|---:|---:|
|DS16|63|1|1|1|
|DS17|51|1|1|1|
|DS18|34|1|1|1|
|POST18-development|45|1|1|1|

`coverage-report.json` records every member/status, recovery qualification, trigger/fallback, runtime/source metrics and matched arms. Archived85 controls are distinct from current B7 baselines; frequency-fit effects are separate from position accuracy.

```json
{
  "full_membership": 193,
  "terminal_members": 4,
  "full_census_position_metrics_withheld": true,
  "arms": {
    "fitted-c": {
      "matched_position_count": 4,
      "missing_or_failed_positions": 189,
      "full_census_metrics_withheld": true
    },
    "zero-c": {
      "matched_position_count": 4,
      "missing_or_failed_positions": 189,
      "full_census_metrics_withheld": true
    }
  }
}
```
